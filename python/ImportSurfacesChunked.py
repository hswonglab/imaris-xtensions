#  ImportSurfacesChunked: An Imaris XTension to import surfaces (chunked).
#
#  Copyright © 2023-2026 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang. Based off of ImportSurfaces.py.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Import Surfaces (Chunked)" icon="Python3" tooltip="Import surface objects using chunked ISurfaces containers for speed.">
#         <Command>Python3XT::ImportSurfacesChunked(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ImportSurfacesChunked imports surfaces into Imaris the same way
ImportSurfaces does, but splits the surface set across multiple ISurfaces
containers instead of adding every surface to a single one.

Why: ImageImportSurfaces() in ImportSurfaces.py calls AddSurface() on one
ISurfaces object once per surface. Import throughput drops off nonlinearly as
that single container accumulates surfaces (measured effective exponent
~1.7 on n=10,000..40,726), so a 100k+ surface set takes much longer per-
surface near the end of the import than at the start. This version adds
surfaces to a rotating set of smaller ISurfaces containers ("chunks") instead
of one large one, then groups the chunks under a single Group node in the
Surpass scene so they still present as one named item.

Speed-test history 
  n=10,000,  chunk_size=1000: chunked is ~42.5% faster than the original.
  n=40,726,  chunk_size=1000: chunked is ~78.2% faster than the original
             (~4.6x speedup). The chunked advantage grows sharply with n,
             consistent with the original's per-item cost degrading faster
             than linearly as its single container grows.

This module was promoted from ImportSurfaces_beta.py once the above results
confirmed the chunked approach's advantage at production scale. It is kept
as a separate menu item/module from ImportSurfaces.py (rather than merged
in) so the two can still be run back-to-back for comparison and so any
regressions are isolated to one file.

Setting the chunk size >= the number of surfaces in the file reduces this
script to (almost) the same behavior as the non-chunked version, which makes
it useful as an apples-to-apples baseline too.
'''
try:
    import glob
    import gzip
    import logging
    import math
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

# Number of surfaces to add to any one ISurfaces container before rolling over
# to a fresh one. chunk_size=1000 is the value validated so far (see the
# speed-test history above); a chunk-size sweep is planned to check whether a
# different value does even better. Update this default once that sweep
# picks a winner.
DEFAULT_CHUNK_SIZE = 1000

# Characters allowed between an .ims basename and the rest of its JSON's name
# (e.g. img1_surfaces.json), so that img1 does not match img10_surfaces.json.
JSON_NAME_SEPARATORS = '_-. '


class TqdmStreamHandler(logging.StreamHandler):
    """StreamHandler that writes through tqdm.write() to avoid breaking progress bars."""
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=self.stream)
            self.flush()
        except Exception:
            self.handleError(record)


def _show_message_box(show_message_fn, title, message):
    vMessageRoot = Tk()
    vMessageRoot.withdraw()
    try:
        show_message_fn(title, message, parent=vMessageRoot)
    finally:
        vMessageRoot.destroy()


def _json_name_matches(json_name, ims_basename):
    '''Whether a lowercased JSON filename belongs to a lowercased .ims basename:
    the basename followed by a separator (which covers <basename>.json).'''
    vNext = json_name[len(ims_basename):len(ims_basename) + 1]
    return json_name.startswith(ims_basename) and vNext != '' and vNext in JSON_NAME_SEPARATORS


def _invalid_batch_selections(selected_paths, image_folder_path):
    '''Return selected paths that XTBatch can't process: it only opens .ims
    files from the folder of the currently-open image.'''
    vFolder = os.path.normcase(os.path.normpath(image_folder_path))
    return [
        selected_path for selected_path in selected_paths
        if os.path.normcase(os.path.dirname(os.path.normpath(selected_path))) != vFolder
        or not selected_path.lower().endswith('.ims')
    ]


def Main_Chunked(vImarisApplication, vRootTkWindow):
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

    # Step 1: Ask for surface name and chunk size (applies to all modes)
    vSurfaceName = simpledialog.askstring(
        'Surface Name', 'Enter name for imported surfaces:',
        initialvalue='Imported Surfaces',
        parent=vRootTkWindow,
    ) or 'Imported Surfaces'

    vChunkSize = simpledialog.askinteger(
        'Chunk Size',
        'Number of surfaces per ISurfaces container before starting a new one.\n'
        'Set this to a number >= the total surface count to disable chunking\n'
        '(i.e. behave like the non-chunked ImportSurfaces script):',
        initialvalue=DEFAULT_CHUNK_SIZE, minvalue=1,
        parent=vRootTkWindow,
    )
    if vChunkSize is None:
        return

    # Step 2: Ask which mode to run in
    vMode = flexible_mbox(
        'Import Surfaces (Chunked)',
        'Choose how to run the import.\n\n'
        'For batch options, the JSON file for each .ims file is found\n'
        'automatically: the script searches the same folder for a .json or .json.gz file\n'
        'whose name starts with the .ims filename.',
        ['This image only', 'All .ims in folder', 'Choose .ims files'],
        parent=vRootTkWindow,
    )
    if vMode is None:
        return

    image_folder_path = os.path.dirname(image_path)

    ims_basenames = [
        os.path.splitext(filename)[0].lower()
        for filename in os.listdir(image_folder_path) if filename.lower().endswith('.ims')
    ]

    def find_json_paths(file_basename):
        '''Find candidate JSON files for a given .ims basename (no extension).

        An exact <basename>.json or <basename>.json.gz wins. Otherwise the
        basename must be followed by a separator, so that img1 does not pick
        up img10_surfaces.json. A JSON that also matches a longer .ims name in
        the folder belongs to that image, so sample does not pick up
        sample_2_surfaces.json.
        '''
        vPattern = os.path.join(glob.escape(image_folder_path), glob.escape(file_basename))
        matches = sorted(glob.glob(vPattern + '*.json') + glob.glob(vPattern + '*.json.gz'))
        vNames = [os.path.basename(match).lower() for match in matches]
        vBase = file_basename.lower()
        exact = [m for m, n in zip(matches, vNames) if n in (vBase + '.json', vBase + '.json.gz')]
        if exact:
            return exact
        vLongerBasenames = [b for b in ims_basenames if len(b) > len(vBase) and b.startswith(vBase)]
        return [
            m for m, n in zip(matches, vNames)
            if _json_name_matches(n, vBase)
            and not any(_json_name_matches(n, b) for b in vLongerBasenames)
        ]

    skipped_images = []

    def batch_json_arg(file_basename):
        json_paths = find_json_paths(file_basename)
        if len(json_paths) != 1:
            skipped_images.append(file_basename + '.ims')
        if not json_paths:
            raise FileNotFoundError(f'No JSON file found for {file_basename} in {image_folder_path}')
        if len(json_paths) > 1:
            raise RuntimeError(
                f'Multiple JSON files found for {file_basename}: '
                + ', '.join(os.path.basename(path) for path in json_paths)
            )
        return (json_paths[0],)

    failed_images = []

    def batch_import(vImarisApplication, *args):
        '''Import one batch image, logging failures so the batch continues.'''
        try:
            ImageImportSurfacesChunked(vImarisApplication, *args)
        except Exception:
            failed_image = vImarisApplication.GetCurrentFileName()
            failed_images.append(failed_image)
            logging.exception('Failed to import surfaces into %s, continuing with the next file', failed_image)

    def log_batch_summary():
        if skipped_images:
            logging.warning(
                '%d file(s) skipped for a missing or ambiguous JSON, see warnings above:\n%s',
                len(skipped_images), '\n'.join(skipped_images),
            )
        if failed_images:
            logging.warning(
                '%d file(s) failed to import, see errors above:\n%s',
                len(failed_images), '\n'.join(failed_images),
            )

    if vMode == 'This image only':
        vFilePath = filedialog.askopenfilename(
            title='Select JSON representing Imaris surfaces',
            filetypes=[('JSON files', '*.json *.json.gz'), ('All files', '*.*')],
            parent=vRootTkWindow,
        )
        if not vFilePath:
            return
        logging.info('Importing surfaces into %s from %s', image_path, vFilePath)
        ImageImportSurfacesChunked(vImarisApplication, vSurfaceName, vChunkSize, vFilePath)

    elif vMode == 'All .ims in folder':
        logging.info('Importing surfaces into all .ims files in %s', image_folder_path)
        XTBatch(
            vImarisApplication,
            fn=batch_import,
            args=(vSurfaceName, vChunkSize),
            im_args_func=batch_json_arg,
            operate_on_image=False,
            save=False,
        )
        log_batch_summary()
        logging.info('Finished batch import for folder %s', image_folder_path)

    elif vMode == 'Choose .ims files':
        selected_paths = filedialog.askopenfilenames(
            title='Select .ims files to import surfaces into',
            initialdir=image_folder_path,
            filetypes=[('IMS files', '*.ims')],
            parent=vRootTkWindow,
        )
        if not selected_paths:
            return
        invalid_paths = _invalid_batch_selections(selected_paths, image_folder_path)
        if invalid_paths:
            messagebox.showerror(
                'Invalid selection',
                f'Selected files must be .ims files in {image_folder_path}:\n\n'
                + '\n'.join(invalid_paths),
                parent=vRootTkWindow,
            )
            return
        selected_filenames = [os.path.basename(selected_path) for selected_path in selected_paths]
        logging.info('Importing surfaces into %d selected .ims files', len(selected_filenames))
        XTBatch(
            vImarisApplication,
            fn=batch_import,
            args=(vSurfaceName, vChunkSize),
            im_args_func=batch_json_arg,
            operate_on_image=False,
            save=False,
            filenames=selected_filenames,
        )
        log_batch_summary()
        logging.info('Finished selected-file batch import')


def ImageImportSurfacesChunked(
    vImarisApplication, vSurfaceName, vChunkSize, vFilePath,
    save_suffix='-imported_surfaces_chunked',
):
    vStartTime = time.time()
    image_path = vImarisApplication.GetCurrentFileName()
    with (gzip.open if vFilePath.endswith('.gz') else open)(vFilePath, 'rb') as f:
        vSurfaceJson = orjson.loads(f.read())

    if not isinstance(vSurfaceJson, list):
        raise RuntimeError('Surface JSON must be a top-level list of surface records')

    vTotal = len(vSurfaceJson)
    vNumChunks = max(1, math.ceil(vTotal / vChunkSize))
    logging.info(
        'Importing %d surfaces in %d chunk(s) of up to %d surfaces each',
        vTotal, vNumChunks, vChunkSize,
    )

    n_skipped = 0
    vChunkSurfacesList = []
    vChunkTimings = []

    for vChunkIndex in range(vNumChunks):
        vChunkStartTime = time.time()
        vChunkStart = vChunkIndex * vChunkSize
        vChunkEnd = min(vChunkStart + vChunkSize, vTotal)
        vChunkJson = vSurfaceJson[vChunkStart:vChunkEnd]

        vSurfaces = vImarisApplication.GetFactory().CreateSurfaces()

        for vSurfaceJsonData in tqdm(
            vChunkJson, desc=f'Importing chunk {vChunkIndex + 1}/{vNumChunks}'
        ):
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

            # add aSurfaceData to this chunk's Surfaces container
            try:
                vSurfaces.AddSurface(aSurfaceData, 0)  # second number is time index which is irrelevant
            except Exception as e:
                logging.warning(f'Failed to add surface:\n{e}')
                logging.warning(f'The skipped surface:\n{vData}')
                n_skipped += 1

        vChunkName = vSurfaceName if vNumChunks == 1 else f'{vSurfaceName} [{vChunkIndex + 1}/{vNumChunks}]'
        vSurfaces.SetName(vChunkName)
        vChunkSurfacesList.append(vSurfaces)

        vChunkElapsed = time.time() - vChunkStartTime
        vChunkCount = len(vChunkJson)
        vChunkTimings.append((vChunkCount, vChunkElapsed))
        logging.info(
            'Chunk %d/%d: added %d surfaces in %.2f minutes (%.3f sec/surface)',
            vChunkIndex + 1, vNumChunks, vChunkCount, vChunkElapsed / 60,
            vChunkElapsed / vChunkCount if vChunkCount else 0.0,
        )

    # Add to scene. If there's more than one chunk, group them under a single
    # named Group node so the chunked import still presents as one item, the
    # same way the non-chunked version does.
    vScene = vImarisApplication.GetSurpassScene()
    if vNumChunks == 1:
        vScene.AddChild(vChunkSurfacesList[0], -1)
    else:
        vGroup = vImarisApplication.GetFactory().CreateDataContainer()
        vGroup.SetName(vSurfaceName)
        for vChunkSurfaces in vChunkSurfacesList:
            vGroup.AddChild(vChunkSurfaces, -1)
        vScene.AddChild(vGroup, -1)

    vElapsedTime = (time.time() - vStartTime) / 60
    logging.info(
        'Imported %d/%d surfaces (%d skipped) in %.2f minutes across %d chunk(s)',
        vTotal - n_skipped, vTotal, n_skipped, vElapsedTime, vNumChunks,
    )
    for vChunkNum, (vChunkCount, vChunkElapsed) in enumerate(vChunkTimings, start=1):
        logging.info(
            '  chunk %d: %d surfaces, %.2f min, %.3f sec/surface',
            vChunkNum, vChunkCount, vChunkElapsed / 60,
            vChunkElapsed / vChunkCount if vChunkCount else 0.0,
        )

    # Save to a new file with suffix — I can't make Imaris overwrite the currently open file
    vBase, vExt = os.path.splitext(image_path)
    vSavePath = f'{vBase}{save_suffix}{vExt}'
    logging.info('Saving to %s', vSavePath)
    vImarisApplication.FileSave(vSavePath, '')
    logging.info('Finished importing surfaces into %s', vSavePath)


def ImportSurfacesChunked(aImarisId):
    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = Tk()
    vRootTkWindow.withdraw()

    # Check if the object is valid
    if vImarisApplication is None:
        vRootTkWindow.destroy()
        _show_message_box(
            messagebox.showerror,
            'Error',
            f'Failed to connect to Imaris application (id={aImarisId})',
        )
        return

    print(f'Connected to Imaris application (id={aImarisId})')

    try:
        Main_Chunked(vImarisApplication, vRootTkWindow)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    vRootTkWindow.destroy()
    _show_message_box(messagebox.showinfo, 'Complete', 'The XTension has terminated.')
