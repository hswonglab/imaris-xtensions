#  GetDimensions: An Imaris XTension to retrieve image dimensions in real units.
#
#  Copyright © 2025 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Get Dimensions" icon="Python3" tooltip="Retrieve image dimensions.">
#         <Command>Python3XT::GetDimensions(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>


# Essential dependencies.
try:
    import csv
    import logging
    import os
    import traceback

    import ImarisLib

    from tkinter import *
    from tkinter import messagebox
    from tkinter import filedialog
except Exception as e:
    print(e)
    input('Press enter to exit.')
    raise e

# Optional dependencies.
try:
    from XTBatch import XTBatch
    batch_enabled = True
except Exception as exception:
    print('Importing XTBatch failed. Batching will be unavailable.')
    print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    batch_enabled = False


def Main(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()
    image_filename = os.path.basename(image_path)
    image_dir = os.path.dirname(image_path)
    out_path = os.path.join(image_dir, 'dimensions.csv')

    # Get the image
    assert vImarisApplication.GetNumberOfImages() == 1
    vImage = vImarisApplication.GetImage(0)
    with open(out_path, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            image_filename,
            vImage.GetExtendMinX(),
            vImage.GetExtendMaxX(),
            vImage.GetExtendMinY(),
            vImage.GetExtendMaxY(),
            vImage.GetExtendMinZ(),
            vImage.GetExtendMaxZ(),
        ])


def GetDimensions(aImarisId):
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

    batched = batch_enabled & messagebox.askyesno(
        'Batched Operation',
        'Would you like to run this XTension on all .ims files in this folder?',
    )
    if batched:
        try:
            XTBatch(vImarisApplication, Main, operate_on_image=False, save=False)
        except Exception as exception:
            print(traceback.print_exception(type(exception), exception, exception.__traceback__))
            messagebox.showerror('Error', 'Failure while running batch.')
            return
    else:
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showerror('Error', 'Only 1 image may be open at a time for this XTension')
            return
        vImage = vImarisApplication.GetImage(0)
        try:
            Main(vImage)
        except Exception as exception:
            print(traceback.print_exception(type(exception), exception, exception.__traceback__))
            messagebox.showerror('Error', 'Failure while running un-batched.')
            return

    messagebox.showinfo('Complete', 'The XTension has terminated.')
