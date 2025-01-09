#  DuplicateChannel: An Imaris XTension to duplicate a select channel (a feature which inexplicably does not exist)
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Duplicate Channel" icon="Python3" tooltip="Duplicates channel.">
#         <Command>Python3XT::DuplicateChannel(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''DuplicateChannel allows for the duplication of a select channel.

This XTension supports batch operations. The user will be prompted to choose
whether all .ims files in the directory of the current image shall be modified

Script heavily inspired by https://github.com/cvbi/python-XTensions/blob/master/XT_duplicate_channel.py
Modified by Amy Huang
'''

#essential dependencies
try:
    import ImarisLib
    import numpy as np
    from tqdm import tqdm
    import tkinter as tk
    import traceback
    from tqdm.contrib.itertools import product
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
    input("Press enter to exit;")

def DuplicateChannel(aImarisId):
    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Check if the object is valid
    if vImarisApplication is None:
        tk.messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return
    
    print(f'Connected to Imaris application (id={aImarisId})')

    # Get channels
    vImage = vImarisApplication.GetImage(0)
    nChannels = vImage.GetSizeC()
    channel_list = range(1, nChannels + 1)
    nTime = vImage.GetSizeT()

    # Select channel
    channel_selected = create_window_from_list(channel_list, window_title = "Select channel:")
    ch_in = np.int64(channel_selected)
    ch_in_name = vImage.GetChannelName(ch_in - 1)
    print(f'Channel name: {ch_in_name}')

    if batch_enabled:
        batched=tk.messagebox.askyesno(
            'Batched Operation.',
            'Would you like to apply changes to all .ims files in this folder?'
        )
    else:
        batched=False

    if batched: 
        try: 
            XTBatch(vImarisApplication, RunDuplicateChannel, (ch_in, True))
        except Exception as e: 
            print(e)
            input("Press enter to exit;")
    else: 
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            tk.messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return
        
        try: 
            vImageNew = RunDuplicateChannel(vImage, ch_in)
            vImarisApplication.SetImage(0, vImageNew)
        except Exception as e: 
            print(e)
            input("Press enter to exit;")

    tk.messagebox.showinfo('Complete', 'The XTension has terminated.')

def RunDuplicateChannel(vImage, ch_in, verbose=True): 

    # get channels
    nChannels = vImage.GetSizeC()
    channel_list = range(1, nChannels + 1)
    nTime = vImage.GetSizeT()
    ch_in_name = vImage.GetChannelName(ch_in - 1)

    # add channel and rename
    ch_out = nChannels + 1
    ch_out_name = f'{ch_in_name} - Duplicate'

    vImageNew = vImage.Clone()
    vImageNew.SetSizeC(ch_out)
    vImageNew.SetChannelName(ch_out - 1, ch_out_name)

    ### slice by slice copying originally developed by Eric in LinearUnmixing.py; modified for these purposes here

    #process data slice by slice in square windows of length vWindowSize pixels
    vWindowSize = 10000 # larger windows can speed up execution but will be more memory-intensive
    vNumChannels = vImage.GetSizeC()
    vNumSlices = vImage.GetSizeZ()
    vXSize = vImage.GetSizeX()
    vYSize=vImage.GetSizeY()
    
    if verbose: 
        print("Duplicating channel...")
    for x,y,z in product(range(0,vXSize,vWindowSize),range(0,vYSize,vWindowSize),range(vNumSlices)):
        window_x_len=min(vWindowSize,vXSize-x)
        window_y_len=min(vWindowSize,vYSize-y)
        vImageArray=np.zeros((window_x_len,window_y_len)) # container for subslice of image as numpy array for one channel

        vImageArray=np.array([np.frombuffer(row,dtype=np.uint8) for row in vImage.GetDataSubSliceBytes(aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=ch_in - 1,aIndexT=0,aSizeX=window_x_len,aSizeY=window_y_len)])
        data_channel_colortable = vImage.GetChannelColorTable(aIndexC=ch_in - 1)
        
        vImageNew.SetDataSubSliceBytes(aData=[row.tobytes() for row in vImageArray],aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=ch_out - 1,aIndexT=0)
        vImageNew.SetChannelColorTable(ch_out - 1, data_channel_colortable.mColorRGB, data_channel_colortable.mAlpha)

    return vImageNew



# All credit goes to https://github.com/cvbi/cvbi/blob/master/gui.py
def create_window_from_list(object_list, window_title='Select one', w=500, h=800):
    """
    Create a selection window from provided list

    :param object_list: List to create a button selector
    :param window_title: Window title
    :param w: width of the window, default = 500
    :param h: height of the window, default = 800

    :return: Creates a window
    """

    window = tk.Tk()
    window.title(window_title)
    window.geometry(str(w)+"x"+str(h))

    object_select = tk.StringVar()
    object_select.set(object_list[0])
    header = tk.Label(master=window, textvariable=object_select)
    header.pack()

    for item in object_list:
        selection_button = tk.Radiobutton(window, text=item, variable=object_select, value=item)
        selection_button.pack()

    closing_button = tk.Button(master=window, text='Selection Complete', command=window.destroy)
    closing_button.pack()

    window.mainloop()

    object_string = object_select.get()

    return(object_string)
