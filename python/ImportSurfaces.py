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
    import glob
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
    from dialog import flexible_mbox
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

def Main(vImarisApplication, vRootTkWindow):
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


    # Step 1: Ask for surface name (applies to all modes)
    vSurfaceName = simpledialog.askstring(
        'Surface Name', 'Enter name for imported surfaces:',
        initialvalue='Imported Surfaces'
    ) or 'Imported Surfaces'

    # Step 2: Ask which mode to run in
    vMode = flexible_mbox(
        'Import Surfaces',
        'Choose how to run the import.\n\n'
        'For batch options, the JSON file for each .ims file is found\n'
        'automatically: the script searches the same folder for a .json file\n'
        'whose name starts with the .ims filename.',
        ['This image only', 'All .ims in folder', 'Choose .ims files'],
        parent=vRootTkWindow,
    )
    if vMode is None:
        return

    image_folder_path = os.path.dirname(image_path)

    def find_json_path(file_basename, log_missing=True):
        '''Find the JSON file for a given .ims basename (no extension).'''
        matches = sorted(glob.glob(os.path.join(image_folder_path, file_basename + '*.json')))
        if not matches:
            if log_missing:
                logging.warning('No JSON file found for %s in %s', file_basename, image_folder_path)
            return None
        if len(matches) > 1:
            logging.warning('Multiple JSON files found for %s, using %s', file_basename, matches[0])
        return matches[0]

    def batch_json_arg(file_basename):
        json_path = find_json_path(file_basename, log_missing=False)
        if json_path is None:
            raise FileNotFoundError(f'No JSON file found for {file_basename} in {image_folder_path}')
        return (json_path,)

    if vMode == 'This image only':
        vFilePath = filedialog.askopenfilename(
            title='Select JSON representing Imaris surfaces',
            filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
            parent=vRootTkWindow,
        )
        if not vFilePath:
            return
        logging.info('Importing surfaces into %s from %s', image_path, vFilePath)
        ImageImportSurfaces(vImarisApplication, vSurfaceName, vFilePath)

    elif vMode == 'All .ims in folder':
        logging.info('Importing surfaces into all .ims files in %s', image_folder_path)
        XTBatch(
            vImarisApplication,
            fn=ImageImportSurfaces,
            args=(vSurfaceName,),
            im_args_func=batch_json_arg,
            operate_on_image=False,
            save=False,
        )
        logging.info('Finished batch import for folder %s', image_folder_path)

    elif vMode == 'Choose .ims files':
        selected_paths = filedialog.askopenfilenames(
            title='Select .ims files to import surfaces into',
            initialdir=image_folder_path,
            filetypes=[('IMS files', '*.ims'), ('All files', '*.*')],
            parent=vRootTkWindow,
        )
        if not selected_paths:
            return
        selected_filenames = [os.path.basename(selected_path) for selected_path in selected_paths]
        logging.info('Importing surfaces into %d selected .ims files', len(selected_filenames))
        XTBatch(
            vImarisApplication,
            fn=ImageImportSurfaces,
            args=(vSurfaceName,),
            im_args_func=batch_json_arg,
            operate_on_image=False,
            save=False,
            filenames=selected_filenames,
        )
        logging.info('Finished selected-file batch import')

def ImageImportSurfaces(vImarisApplication, vSurfaceName, vFilePath, save_suffix='-imported_surfaces'):
    vStartTime = time.time()
    image_path = vImarisApplication.GetCurrentFileName()
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
        'Imported %d/%d surfaces (%d skipped) in %.2f minutes',
        len(vSurfaceJson) - n_skipped,
        len(vSurfaceJson),
        n_skipped,
        vElapsedTime,
    )
    vBase, vExt = os.path.splitext(image_path)
    vSavePath = f'{vBase}{save_suffix}{vExt}'
    logging.info('Saving to %s', vSavePath)
    vImarisApplication.FileSave(vSavePath, '')
    logging.info('Finished importing surfaces into %s', vSavePath)

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
        Main(vImarisApplication, vRootTkWindow)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
    vRootTkWindow.destroy()
