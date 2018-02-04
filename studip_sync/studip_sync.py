import shutil
import os
import tempfile
import zipfile
import glob
import subprocess
import requests

from time import sleep
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException

from studip_sync.config import config

class DownloadError(Exception):
    pass

class ExtractionError(Exception):
    pass

class StudipSync(object):

    def __init__(self):
        super(StudipSync, self).__init__()
        self.workdir = tempfile.mkdtemp(prefix="studip-sync")
        self.download_dir = os.path.join(self.workdir, "zips")
        self.extract_dir = os.path.join(self.workdir, "extracted")
        self.destination_dir = config.target

        os.makedirs(self.download_dir)
        os.makedirs(self.extract_dir)
        os.makedirs(self.destination_dir, exist_ok=True)

    def sync(self):
        extractor = Extractor(self.extract_dir)
        rsync = RsyncWrapper()

        print("Logging in...")
        with Downloader(self.download_dir, config.username, config.password) as downloader:
            for course in config.courses:
                print("Downloading '" + course["save_as"] + "'...")
                try:
                    zip_location = downloader.download(course["course_id"], course.get("sync_only"))
                    extractor.extract(zip_location, course["save_as"])
                except DownloadError as e:
                    print("ERROR: Download failed for '" + course["save_as"] + "'")
                    print("       Possible Reasons:")
                    print("       - Folder is bigger than 100MB (Stud.IP does not allow downloads > 100MB)")
                    print("       - You are not subscribed to the course and cannot access files")
                except ExtractionError as e:
                    print("ERROR: Extraction failed for '" + course["save_as"] + "'")

        print("Synchronizing with existing files...")
        rsync.sync(self.extract_dir + "/", self.destination_dir)

    def cleanup(self):
        shutil.rmtree(self.workdir)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()


class RsyncWrapper(object):

    def __init__(self):
        super(RsyncWrapper, self).__init__()
        timestr = datetime.strftime(datetime.now(), "%Y-%m-%d_%H+%M+%S")
        self.suffix = "_" + timestr + ".old"

    def sync(self, source, destination):
        subprocess.call(["rsync", "--recursive", "--checksum", "--backup", "--suffix=" + self.suffix,
                        source, destination])

class Extractor(object):

    def __init__(self, basedir):
        super(Extractor, self).__init__()
        self.basedir = basedir

    @staticmethod
    def remove_intermediary_dir(extracted_dir):
        subdirs = os.listdir(extracted_dir)
        if len(subdirs) == 1:
            for filename in glob.iglob(os.path.join(extracted_dir, subdirs[0], "*")):
                shutil.move(filename, extracted_dir)
            os.rmdir(os.path.join(extracted_dir, subdirs[0]))

    @staticmethod
    def remove_empty_dirs(directory):
        for root, dirs, files in os.walk(directory):
            if not dirs and not files:
                os.rmdir(root)

    def extract(self, archive_filename, destination, cleanup=True):
        try:
            with zipfile.ZipFile(archive_filename, "r") as z:
                destination = os.path.join(self.basedir, destination)
                z.extractall(destination)
                if cleanup:
                    self.remove_intermediary_dir(destination)
                    self.remove_empty_dirs(destination)

                return destination
        except zipfile.BadZipFile:
            raise ExtractionError("Cannot extract file: " + archive_filename)


class Downloader(object):

    def __init__(self, workdir, username, password):
        super(Downloader, self).__init__()
        self.workdir = workdir

        options = Options()
        options.add_argument("--headless")
        self.driver = webdriver.Firefox(firefox_options=options)
        self.driver.implicitly_wait(10)
        self._login(username, password)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.driver.close()

    def _login(self, username, password):
        self.driver.get("https://studip.uni-passau.de/studip/index.php?again=yes&sso=shib")

        username_element = self.driver.find_element_by_id("username")
        username_element.clear()
        username_element.send_keys(username)

        password_element = self.driver.find_element_by_id("password")
        password_element.clear()
        password_element.send_keys(password)
        password_element.send_keys(Keys.ENTER)

        try:
            element = WebDriverWait(self.driver, 7).until(
                expected_conditions.presence_of_element_located((By.ID, "footer"))
            )
        except:
            # TODO Improve exception handling
            print("Login failed!")
            print("Aborting")
            self.driver.quit()
            exit(1)

    def download(self, course_id, sync_only=None):
        self.driver.get("https://studip.uni-passau.de/studip/dispatch.php/course/files?cid=" + course_id)

        try:
            folder_id = self.driver.find_element_by_name("parent_folder_id").get_attribute("value")
        except NoSuchElementException:
            raise DownloadError("Could not locate parent folder for course: " + course_id)

        params = {"cid": course_id}
        url = "https://studip.uni-passau.de/studip/dispatch.php/file/bulk/" + folder_id
        csrf_token = self.driver.execute_script("return STUDIP.CSRF_TOKEN.value")
        data = {
            "security_token": csrf_token,
            # "parent_folder_id": folder_id,
            "ids[]": sync_only or folder_id,
            "download": 1
        }

        selenium_cookies = self.driver.get_cookies()
        cookie_jar = requests.cookies.RequestsCookieJar()
        for cookie in selenium_cookies:
            cookie_jar.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])

        with requests.post(url, params=params, data=data, cookies=cookie_jar, stream=True) as r:
            if not r.ok:
                raise DownloadError("Download failed " + url)
            path = os.path.join(self.workdir, course_id)
            with open(path, "wb") as f:
                shutil.copyfileobj(r.raw, f)
                return path
