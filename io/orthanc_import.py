#!/usr/bin/env python

# This script is used to import dicom files (zipped) into local orthanc server


import os.path
import glob 
import sys
import shutil
import zipfile
import tempfile
import httpx
import requests
import logging
import pathlib

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from split_file_reader import SplitFileReader
from pyorthanc import Orthanc
from requests.auth import HTTPBasicAuth


def UploadBuffer(dicom, dicom_path, ignore_errors=True, verbose=True):
    auth = HTTPBasicAuth("dev-user-alta", "SyTP&8JbKFx@a6R65^sE`Z$")
    url = "http://localhost:8042"
    r = requests.post('%s/instances' % url, auth = auth, data = dicom)
   
    # orthanc = Orthanc('http://localhost:8042')
    # orthanc.setup_credentials('demo', 'demo')  # If needed

    try:
        r.raise_for_status()
    except:
        if ignore_errors:
            if verbose:
                logging.warning(f'Not a valid DICOM file ignoring it... {dicom_path}')
            return
        else:
            raise


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
                logging.info(f"pswd \"{pswd}\" did pass...")

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
                pswd = select_right_pswd(zip_file, ["ALTAbielefeld2020", "ALTAbi2020!!", 'LucasALTA22!!', 
                                                    "ALTAbielefeld2021", "ALTAbi2021!!"])

                if pswd is None:
                    logging.warning("No psw did pass. Aborting import...")
                    return
                zip_file.setpassword(pwd = bytes(pswd, 'utf-8'))
                
                iterations = 0
                name_list = zip_file.namelist()
                
                for member in zip_file.namelist():
                    
                    filename = os.path.basename(member)
                    iterations += 1
                    
                    if True:
                    
                        # skip directories
                        if not filename:
                            continue
                        try:                            
                            # with zip_file.open(member, mode='r', pwd=bytes(pswd, 'utf-8')) as zf:
                            dicom = zip_file.read(member, pwd=bytes(pswd, 'utf-8'))

                            if iterations % 1000 == 0:
                                logging.info(f"{iterations}/{len(name_list)} Posting to orthanc... {member}")
                            UploadBuffer(dicom, dicom_path=member)
                                
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
        
        
def get_main_args_eval():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    arg = parser.add_argument
    arg("--dir", nargs='+', help="Folder(s) with zips...")
    args = parser.parse_args()
    return args


if __name__=="__main__":
    args = get_main_args_eval()
    print(args.dir)
    
    for path_dir in args.dir:
        
        logname = os.path.join(pathlib.Path(__file__).parent.resolve(), 
                            f"unzip_{os.path.basename(path_dir)}.log")

        file_handler = logging.FileHandler(filename=logname)
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        handlers = [file_handler, stdout_handler]

        logging.basicConfig(format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.INFO,
                            handlers=handlers)

        logging.info("Running unzipping script...")
        
        try:
            # get all splitted zips
            splitted_zips = glob.glob(os.path.join(path_dir, "*zip.001"))
            splitted_zips = [sorted(glob.glob(".".join([os.path.splitext(filename)[0], "*"]))) for filename in splitted_zips]

            # get all normal zips
            non_splitted_zips = [[i] for i in sorted(glob.glob(os.path.join(path_dir, "*zip")))]
            filepaths_archived = splitted_zips + non_splitted_zips
            
            total = len(filepaths_archived)
            logging.info(f"Total archives to process {len(filepaths_archived)}... {filepaths_archived}")
            for i, filepaths in enumerate(filepaths_archived):
            # if True:
                logging.info(f"{i + 1}/{total} Processing archive: {filepaths}")
                status = unzip_data(filepaths)
                if status:
                    logging.info(f"Success for {filepaths}")
                    for filepath in filepaths:
                        logging.info(f"Moving {filepath} to /hdd/drive1/oleksii/mrt_zips_unzipped_new/")
                        
                        shutil.move(filepath, "/hdd/drive1/oleksii/mrt_zips_unzipped_new")
                else:
                    logging.warning(f"Archives need to be double-checked for {filepaths}")
        except Exception as e:
            logging.error('Catch all:', exc_info=e)

