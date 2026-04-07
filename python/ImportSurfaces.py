#  ImportSurfaces: An Imaris XTension to export surfaces.
#
#  Copyright © 2023-2025 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang. Based off of ExportSurfaces.py by Chris Skalnik. 
#
#    <CustomTools>
#      <Menu>
#       <Item name="Import Surfaces" icon="Python3" tooltip="Import surface objects.">
#         <Command>Python3XT::ImportSurfaces(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ImportSurfaces exports the surfaces in an Imaris file for use outside Imaris.
'''
try:
    import logging
    import os
    import sys
    import time
    import traceback
    from tqdm import tqdm

    import ImarisLib
    import Imaris
    import orjson

    from tkinter import Tk
    from tkinter import messagebox
    from tkinter import filedialog
    from tkinter import simpledialog
    from XTBatch import XTBatch
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise

# Some DLLs are stored at this path, but it isn't correctly set by default. We
# can't just set the system environment variable because doing so adds a space
# at the end of the path for some reason. This means that instead of searching
# for \path\to\bin\myDll.dll, it searches for \path\to\bin\ myDll.dll.
DLL_PATH = os.path.join(os.path.dirname(sys.executable), 'Library', 'bin')
os.environ['PATH'] += f';{DLL_PATH}'

import numpy as np

LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'

class TqdmStreamHandler(logging.StreamHandler):
    """StreamHandler that writes through tqdm.write() to avoid breaking progress bars."""
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=self.stream)
            self.flush()
        except Exception:
            self.handleError(record)

def Main(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    logging.basicConfig(
        format=LOG_FORMAT,
        level=logging.INFO,
        handlers=[
            logging.FileHandler(logpath),
            TqdmStreamHandler(sys.stdout),
        ]
    )

    # Get the image and channels
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return

    
    logging.info('Asking user to select json')
    vFilePath = filedialog.askopenfilename(title='Select json representing Imaris surfaces')
    if not vFilePath:
        return
    
    vSurfaceName = simpledialog.askstring(
        'Surface Name', 'Enter name for imported surfaces:',
        initialvalue='Imported Surfaces'
    ) or 'Imported Surfaces'

    batched=messagebox.askyesno(
        'Batched Operation.',
        'Would you like to apply changes to all .ims files in this folder?  \n' \
        'If yes, the name of the selected .json file must begin with the name of the selected .ims file.'
    )    

    if batched:
        vBase, _ = os.path.splitext(image_path)
        vFilePath=vFilePath.replace('/','\\')
        if vFilePath[:len(vBase)]==vBase:
            json_suffix=vFilePath[len(vBase):]
            image_folder_path='\\'.join(image_path.split('\\')[:-1])
        else:
            raise Exception('Name of selected .json file does not begin with the name of the selected .ims file.')
        XTBatch(vImarisApplication,fn=ImageImportSurfaces,args=(vSurfaceName,),
                im_args_func=lambda FileName:(image_folder_path+'\\'+FileName+json_suffix,),operate_on_image=False)
    else:
        ImageImportSurfaces(vImarisApplication,vSurfaceName,vFilePath)
        # Save to a new file with suffix — I can't make Imaris overwrite the currently open file
        vBase, vExt = os.path.splitext(image_path)
        vSavePath = f'{vBase}-imported_surfaces{vExt}'
        logging.info('Saving to %s', vSavePath)
        vImarisApplication.FileSave(vSavePath, '')
    



    logging.info('----- Begin importing surfaces to %s -----', image_path)
    logging.info('----- Done importing surfaces -----')

def ImageImportSurfaces(vImarisApplication,vSurfaceName,vFilePath):
    vStartTime = time.time()
    with open(vFilePath, 'rb') as f:
        vSurfaceJson = orjson.loads(f.read())

    vSurfaces = vImarisApplication.GetFactory().CreateSurfaces()

    n_skipped = 0
    logging.info('Importing %d surfaces', len(vSurfaceJson))
    for vSurfaceJsonData in tqdm(vSurfaceJson, desc='Importing'):
        vData = np.array(vSurfaceJsonData['mask'], dtype=np.uint16).transpose([2, 1, 0])
        vSurfaceJsonData['mask'] = None  # free JSON mask data
        vSizeX, vSizeY, vSizeZ = vData.shape

        # create aSurfaceData dataset
        aSurfaceData = vImarisApplication.GetFactory().CreateDataSet()
        aSurfaceData.Create(Imaris.tType.eTypeUInt16, vSizeX, vSizeY, vSizeZ, 1, 1)
        aSurfaceData.SetDataVolumeFloats(vData.tolist(), aIndexC=0, aIndexT=0)

        aSurfaceData.SetExtendMinX(vSurfaceJsonData['xRange'][0])
        aSurfaceData.SetExtendMaxX(vSurfaceJsonData['xRange'][1])

        aSurfaceData.SetExtendMinY(vSurfaceJsonData['yRange'][0])
        aSurfaceData.SetExtendMaxY(vSurfaceJsonData['yRange'][1])

        aSurfaceData.SetExtendMinZ(vSurfaceJsonData['zRange'][0])
        aSurfaceData.SetExtendMaxZ(vSurfaceJsonData['zRange'][1])

        # add aSurfaceData to Surfaces
        try:
            vSurfaces.AddSurface(aSurfaceData, 0) # second number is time index which is irrelevant
        except Exception as e:
            logging.warning(f'Failed to add surface:\n{e}')
            logging.warning(f'The skipped surface:\n{vData}')
            n_skipped += 1

    vSurfaces.SetName(vSurfaceName)

    # add to scene
    vScene = vImarisApplication.GetSurpassScene()
    vScene.AddChild(vSurfaces, -1)

    vElapsedTime = (time.time() - vStartTime)/60
    logging.info(
        f'Imported %d/%d surfaces (%d skipped) in %.2f minutes',
        len(vSurfaceJson) - n_skipped,
        len(vSurfaceJson),
        n_skipped,
        vElapsedTime,
    )

def ImportSurfaces(aImarisId):
    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = Tk()
    vRootTkWindow.withdraw()

    # Check if the object is valid
    if vImarisApplication is None:
        messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return

    print(f'Connected to Imaris application (id={aImarisId})')

    try:
        Main(vImarisApplication)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
