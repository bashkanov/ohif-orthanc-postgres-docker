# merge cases
import os
import shutil

# target = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-zone.alta-ai.com-img"
# destination = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-multimodal-img"

target = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-zone.alta-ai.com-seg"
destination = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-multimodal-seg"

for soid in os.listdir(target):
    target_path = os.path.join(target, soid)
    destination_path = os.path.join(destination, soid)
    print(target_path, destination_path)
    shutil.move(target_path, destination_path)