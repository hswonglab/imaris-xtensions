#  ConfigureChannels: An Imaris XTension to apply stored settings to channels
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik and Eric Gai.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Configure Channels" icon="Python3" tooltip="Apply stored settings to channels.">
#         <Command>Python3XT::ConfigureChannels(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ConfigureChannels allows loading channel names and colors from a CSV file.

The CSV should have one row per channel, in the order in which those channels
appear in Imaris, where each row has the following columns:

* channel: Intended to be the index (1-indexed) of the channel, but ignored by
  this code.
* setting: Intended to be the sequential (a.k.a. setting) number in LAS X, but
  ignored by this code.
* fluorophore: The fluorophore being detected by the channel, for example
  "AF555".
* target: The protein or other cell feature that is supposed to be labeled by
  the fluorophore.
* color: The RGB color in which to display the channel, represented as 3
  hexadecimal bytes (e.g. `ffffff` for white or `ff0000` for red).

An error will be thrown if the first row of the CSV (the header) does not have
exactly these columns, in this order.

This XTension supports batch operations. The user will be prompted to choose 
whether all .ims files in the directory of the current image shall be modified. 

Whenever this XTension operates on a file, it tracks all changes in a log file.
If the file currently opened is at path `path`, then the log file is at
`path.txt`. When called in batch mode, all logs will be written in `path.txt` 
corresponding to the file from which the XTension was called. 

This XTension will only save changes when run in batch mode. Otherwise, 
logged changes may not actually be saved if the user chooses not to.
'''

#essential dependencies
try:
    import csv
    import logging
    import traceback

    import ImarisLib

    from tkinter import *
    from tkinter import messagebox
    from tkinter import filedialog
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise

#nonessential dependences
try:
    from XTBatch import XTBatch
    batch_enabled=True
except Exception as e:
    print(e)
    batch_enabled=False

EXPECTED_HEADER = ['channel', 'setting', 'fluorophore', 'target', 'color']
LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'

def Main(aImarisId):
    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Check if the object is valid
    if vImarisApplication is None:
        messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return
    
    print(f'Connected to Imaris application (id={aImarisId})')

    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    
    logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
    logging.info('----- Begin Editing %s -----', image_path)



    logging.info('Asking user to select panel')
    with filedialog.askopenfile(mode='r', title='Select CSV specifying renaming panel') as f:
        vNewChannelNames,vNewChannelColors=read_panel_csv(f)
        panel_file_path=f.name
    if batch_enabled:
        batched=messagebox.askyesno(
            'Batched Operation.',
            'Would you like to apply changes to all .ims files in this folder?'
        )
    else:
        batched=False

    if batched:
        XTBatch(vImarisApplication,ConfigureImageChannels,(vNewChannelNames,vNewChannelColors,True))
    else:
        # Get the image and channels
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return

        vImage = vImarisApplication.GetImage(0)
        vImageNew=ConfigureImageChannels(vImage,vNewChannelNames,vNewChannelColors)
        vImarisApplication.SetImage(0, vImageNew)
        logging.info('Asking user to save image.')
        saved = messagebox.askyesno(
            'Save changes.',
            'Please save or discard changes. Did you save the file?'
        )
        logging.info('User reports that they saved changes: %s', saved)
        logging.info('----- Done Editing %s -----', image_path)
    print('Changes complete.')

# def configure_channels(vImage,vNewChannelNames=None,vNewChannelColors=None,panel_file_path=None,confirmed=False):
#     vNumChannels = vImage.GetSizeC()
#     vOldChannelNames = [vImage.GetChannelName(i) for i in range(vNumChannels)]
#     vOldChannelColors = [vImage.GetChannelColorRGBA(i) for i in range(vNumChannels)]
#     vOldChannelColorStrings = ['%08x' % color for color in vOldChannelColors]

#     if (vNewChannelNames is None) or (vNewChannelColors is None):
#         if panel_file_path:
#             with open(panel_file_path) as f:
#                 vNewChannelNames,vNewChannelColors=read_panel_csv(f)
#         else:
#             logging.info('Asking user to select panel')
#             with filedialog.askopenfile(mode='r', title='Select CSV specifying renaming panel') as f:
#                 vNewChannelNames,vNewChannelColors=read_panel_csv(f)
#                 panel_file_path=f.name
#     else:
#         logging.info('New channel information provided as arguments.')

#     vNewChannelColorStrings = ['%08x' % color for color in vNewChannelColors]

#     if len(vOldChannelNames) != len(vNewChannelNames):
#         raise RuntimeError(
#             f'Old channels {vOldChannelNames} and new channels '
#             f'{vNewChannelNames} differ in length.'
#         )
#     if len(vOldChannelColorStrings) != len(vNewChannelColorStrings):
#         raise RuntimeError(
#             f'Old channel colors {vOldChannelColorStrings} and new channels '
#             f'{vNewChannelColorStrings} differ in length.'
#         )

#     if not confirmed:
#         confirmed = messagebox.askokcancel(
#             'Confirm Changes',
#             (
#                 f'Rename channels {vOldChannelNames} to {vNewChannelNames} '
#                 f'and re-color from {vOldChannelColorStrings} to {vNewChannelColorStrings}?'
#             )
#         )

#     if confirmed:
#         print(f'Renaming channels {vOldChannelNames} to {vNewChannelNames}.')
#         print(f'Re-coloring from {vOldChannelColorStrings} to {vOldChannelColorStrings}.')
#     else:
#         print('Changes aborted.')
#         return None

#     vImageNew = ConfigureImageChannels(vImage,vNewChannelNames,vNewChannelColors)
#     return vImageNew

def ConfigureImageChannels(vImage,vNewChannelNames,vNewChannelColors,confirmed=False):

    vNumChannels = vImage.GetSizeC()
    vOldChannelNames = [vImage.GetChannelName(i) for i in range(vNumChannels)]
    vOldChannelColors = [vImage.GetChannelColorRGBA(i) for i in range(vNumChannels)]
    vOldChannelColorStrings = ['%08x' % color for color in vOldChannelColors]
    vNewChannelColorStrings = ['%08x' % color for color in vNewChannelColors]
    if len(vOldChannelNames) != len(vNewChannelNames):
        raise RuntimeError(
            f'Old channels {vOldChannelNames} and new channels '
            f'{vNewChannelNames} differ in length.'
        )
    if len(vOldChannelColorStrings) != len(vNewChannelColorStrings):
        raise RuntimeError(
            f'Old channel colors {vOldChannelColorStrings} and new channels '
            f'{vNewChannelColorStrings} differ in length.'
        )

    if not confirmed:
        confirmed = messagebox.askokcancel(
            'Confirm Changes',
            (
                f'Rename channels {vOldChannelNames} to {vNewChannelNames} '
                f'and re-color from {vOldChannelColorStrings} to {vNewChannelColorStrings}?'
            )
        )

    if confirmed:
        print(f'Renaming channels {vOldChannelNames} to {vNewChannelNames}.')
        print(f'Re-coloring from {vOldChannelColorStrings} to {vOldChannelColorStrings}.')
    else:
        print('Changes aborted.')
        return None
    vImageNew=vImage.Clone()
    logging.info('Renaming channels from %s to %s.', vOldChannelNames, vNewChannelNames)
    for i, vNewName in enumerate(vNewChannelNames):
        vImageNew.SetChannelName(i, vNewName)
    logging.info('Channel renaming complete.')
    logging.info('Re-coloring channels from %s to %s', vOldChannelColorStrings, vNewChannelColorStrings)
    for i, vNewColor in enumerate(vNewChannelColors):
        vImageNew.SetChannelColorRGBA(i, vNewColor)
    logging.info('Channel re-coloring complete.')
    return vImageNew


def read_panel_csv(f):
    logging.info('Reading panel from %s', f.name)
    reader = csv.reader(f)
    header = next(reader)
    if header != EXPECTED_HEADER:
        raise RuntimeError(
            f'Panel has unexpected format. Got header {header} instead of {EXPECTED_HEADER}'
        )
        return
    vNewChannelColors = []
    vNewChannelNames = []
    for _, _, fluorophore, target, rgb in reader:
        if len(rgb) != 6:
            raise RuntimeError(f'Invalid color for {fluorophore} {target}: {rgb}')
            return
        vNewChannelNames.append(f'{target} {fluorophore}')
        # The CSV specifies color as RGB
        red = rgb[0:2]
        green = rgb[2:4]
        blue = rgb[4:6]
        # The color is represented as ABGR where each of alpha, blue, green, and red are represented by
        # a byte and A is the most-significant byte. We set an opacity of 0, which indicates no transparency.
        vNewChannelColors.append(int(f'00{blue}{green}{red}', 16))
    return vNewChannelNames,vNewChannelColors

def ConfigureChannels(aImarisId):
    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = Tk()
    vRootTkWindow.withdraw()

    try:
        Main(aImarisId)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
