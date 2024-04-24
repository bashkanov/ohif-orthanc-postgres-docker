import os
import shutil
import glob

hash_len = len("21e363ec8df6845743f28967490f9e7888b42184")

to_rename = glob.glob("/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-orient-Segmentations/*/*")

for name in to_rename:
    dirname = os.path.dirname(name)
    base_name = os.path.basename(name)
    hash_name = base_name[:hash_len]
    new_name = '-'.join([hash_name[i:i+8] for i in range(0, len(hash_name), 8)])
    new_name = '-'.join([new_name, base_name[hash_len:]])
    new_path = os.path.join(dirname, new_name)
    
    print(name, new_path)
    os.rename(name, new_path)

# shutil.rename(fromname, toname)