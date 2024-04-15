from pyorthanc import Orthanc, Study

def get_orthanc_client():
    # Initialize orthanc client
    orthanc = Orthanc('http://localhost:8042')
    orthanc.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$') 
    return orthanc


def sane_filename(filename, keepcharacters=('.','_')):
    return "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()
    