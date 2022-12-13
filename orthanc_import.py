import os.path
import glob 
import sys
import shutil
import zipfile
import tempfile
import httpx

from split_file_reader import SplitFileReader
from pyorthanc import Orthanc
import logging
import pathlib

logname = os.path.join(pathlib.Path(__file__).parent.resolve(), "unzip.log")

file_handler = logging.FileHandler(filename=logname)
stdout_handler = logging.StreamHandler(stream=sys.stdout)
handlers = [file_handler, stdout_handler]

logging.basicConfig(format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.INFO,
                    handlers=handlers)

logging.info("Running unzipping script...")


def select_right_pswd(zip_file, pswds):
    # it also checks for validity of the zip...
    for member in zip_file.namelist():
            # skip directories
            if not os.path.basename(member):
                logging.debug(f"{member} is not file")
                continue
            else:
                logging.debug(f"{member} found file")
                break
            
    for pswd in pswds:
        try:
            with tempfile.TemporaryDirectory() as tmp_dirpath:
                zip_file.extract(member, path=tmp_dirpath, pwd=bytes(pswd, 'utf-8'))
            return pswd
        except zipfile.BadZipFile:
            logging.warning(f"Bad zipfile: {member}")
            return
        except RuntimeError: 
            logging.info(f"pswd did not matched \"{pswd}\". Trying another password...")
            continue


def unzip_data(filepaths):
    with SplitFileReader(filepaths) as sfr:   
        try: 
            with zipfile.ZipFile(sfr, mode='r') as zip_file:
                pswd = select_right_pswd(zip_file, ["ALTAbielefeld2020", "ALTAbi2020!!", 'LucasALTA22!!'])

                if pswd is None:
                    logging.warning("Apparantly Bad zipfile...")
                    return
                zip_file.setpassword(pwd = bytes(pswd, 'utf-8'))
                
                iterations = 0
                name_list = zip_file.namelist()
                
                for member in zip_file.namelist():
                    
                    filename = os.path.basename(member)
                    # skip directories
                    if not filename:
                        continue
                    try:
                        with zip_file.open(member, mode='r', pwd=bytes(pswd, 'utf-8')) as zf:
                            if iterations % 1000 == 0:
                                logging.info(f"{iterations}/{len(name_list)} Posting to orthanc... {member}")
                            orthanc.post_instances(zf)
                            iterations += 1
                    except RuntimeError as err: 
                        logging.error(f"Runtime Error has occured for member {member} : {err}")
                        continue
                    except zipfile.BadZipFile as exc:
                        logging.warning(f"Ingoring member {member} since caught BadZipFile exception : {exc}")
                        continue
                    except httpx.ConnectError as err:
                        logging.critical(f"Connecting problem with orthanc server: {err}")
                        exit(1)
                    
        except zipfile.BadZipFile as exc:
            logging.warning(f"Apparently, {filepaths} did not get all the zip splits... {exc}")
            return
        return 1
        

if __name__=="__main__":
    # test_dicom_path =  "/hdd/drive1/oleksii/mrt_zips/Latest_unpacked/Teil 1/DICOM/00769d60"

    orthanc = Orthanc('http://localhost:8042')
    orthanc.setup_credentials('demo', 'demo')  # If needed

    # filepaths = sorted(glob.glob("/hdd/drive1/oleksii/mrt_zips/2017/2017 Jan - April.zip*"))
    # filepaths_0 = sorted(glob.glob("/hdd/drive1/oleksii/mrt_zips/2022/2022 Januar.zip*")) # with problems
    # filepaths_1 = sorted(glob.glob("/hdd/drive1/oleksii/mrt_zips/2022/2022 September.zip*"))
    # filepaths = sorted(glob.glob("/hdd/drive1/oleksii/mrt_zips/2018/2018 April - Juni.zip*"))

    splitted_zips = glob.glob("/hdd/drive1/oleksii/mrt_zips/2022/*zip.001")
    splitted_zips = [sorted(glob.glob(".".join([os.path.splitext(filename)[0], "*"]))) for filename in splitted_zips]
          
    non_splitted_zips = [[i] for i in sorted(glob.glob("/hdd/drive1/oleksii/mrt_zips/2022/*zip"))]
    filepaths_archived = splitted_zips + non_splitted_zips
    
    total = len(filepaths_archived)
    logging.info(f"Total archives to process {len(filepaths_archived)}...")
    for i, filepaths in enumerate(filepaths_archived):
    # if True:
        logging.info(f"{i + 1}/{total} Processing archive: {filepaths}")
        status = unzip_data(filepaths)
        if status:
            logging.info(f"Success for {filepaths}")
            for filepath in filepaths:
                logging.info(f"Moving {filepath} to /hdd/drive1/oleksii/mrt_zips_unzipped/")
                # shutil.move(filepath, "/hdd/drive1/oleksii/mrt_zips/unarchived/")
        else:
            logging.warning(f"Archives need to be double-checked for {filepaths}")
