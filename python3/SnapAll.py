#  SnapAll: An Imaris XTension to save snapshots of all channels.
#
#  Copyright © 2024 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik.
#
#    <CustomTools>
#      <Menu>
#       <Item name="SnapAll" icon="Python3" tooltip="Save snapshots of all channels.">
#         <Command>Python3XT::SnapAll(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''SnapAll saves snapshots of each channel.

For each channel, one snapshot of just that channel is saved.

Snapshots are saved to the same directory as the Imaris *.ims file and are
named as the Imaris filename, then an underscore, and then the channel name.
Along with each snapshot, a metadata file is generated, which records the
display settings used to create the snapshot.
'''

import re
import traceback

import ImarisLib

from tkinter import *
from tkinter import messagebox
from tkinter import filedialog

VERSION = '0.1.0'

def make_valid_filename(name):
    # Adapted from the Django project, which is Copyright (c) Django Software
    # Foundation and individual contributors.
    name = str(name)
    name = name.strip().replace(' ', '_')
    name = re.sub(r'(?u)[^-\w.]', '', name)
    if name in {'', '.', '..'}:
        raise RuntimeError(f'Failed to make "{name}" into a valid filename.')
    return name

def Main(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()

    # Get the image and channels
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return

    vImage = vImarisApplication.GetImage(0)
    vNumChannels = vImage.GetSizeC()

    # Get camera position information for metadata.
    vCamera = vImarisApplication.GetSurpassCamera()
    vView = [
        vCamera.GetFocus(),
        vCamera.GetHeight(),
        vCamera.GetOrientationAxisAngle().mAngle,
        vCamera.GetOrientationAxisAngle().mAxisXYZ,
        vCamera.GetOrientationQuaternion(),
        vCamera.GetOrthographic(),
        vCamera.GetPosition(),
    ]

    # Turn off all channels.
    for i in range(vNumChannels):
        vImarisApplication.SetChannelVisibility(i, False)

    # Take a snapshot of each channel, one at a time.
    for i in range(vNumChannels):
        vImarisApplication.SetChannelVisibility(i, True)
        vChannelName = make_valid_filename(vImage.GetChannelName(i))
        vSnapshotNameBase = f'{image_path}_{vChannelName}'
        vImarisApplication.SaveSnapShot(f'{vSnapshotNameBase}.tif')
        with open(f'{vSnapshotNameBase}.txt', 'w', encoding='utf-8') as f:
            f.write(f'Snapshot generated by the SnapAll Imarix XTension.\n')
            f.write(f'Channel Name: {vChannelName}\n')
            f.write(f'Channel Index: {i}\n')
            f.write(f'Channel Display Min: {vImage.GetChannelRangeMin(i)}\n')
            f.write(f'Channel Display Max: {vImage.GetChannelRangeMax(i)}\n')
            f.write(f'Channel Display Gamma: {vImage.GetChannelGamma(i)}\n')
            f.write(f'Camera View: {vView}\n')
            f.write(f'View Mode: {vImarisApplication.GetViewer()}\n')
            f.write(f'Imaris Version: {vImarisApplication.GetVersion()}\n')
            f.write(f'SnapAll Version: {VERSION}\n')
        vImarisApplication.SetChannelVisibility(i, False)

    print('Done.')


def SnapAll(aImarisId):
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
