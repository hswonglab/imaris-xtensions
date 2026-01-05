#  Beautify: An Imaris XTension to prepare publication quality images from counting mode
#
#  Copyright © 2025 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Eric Gai.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Beautify" icon="Python3" tooltip="Beautify your image">
#         <Command>Python3XT::Beautify(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''Beautify prepares smoothed images from files acquired in photon counting mode,
which tend to have low pixel values. 

This function will apply a linear stretch to the data, and then apply a Gaussian 
filter. These operations are performed channel-by-channel. The user will be asked to 
provide values for linear scaling, where the provided value will be cast to the maximum 
intensity. The Gaussian filter width has been set to 0.284um by default. This will be 
updated in future developments.  

This XTension supports batch operations. The user will be prompted to choose 
whether all .ims files in the directory of the current image shall be modified. 

Whenever this XTension operates on a file, it tracks all changes in a log file.
If the file currently opened is at path `path`, then the log file is at
`path.txt`. When called in batch mode, all logs will be written in `path.txt` 
corresponding to the file from which the XTension was called. 

This XTension will only save changes when run in batch mode. Otherwise, 
logged changes may not actually be saved if the user chooses not to.
'''

try:
    import csv
    import logging
    import traceback
    import ImarisLib
    from XTBatch import XTBatch
    import tkinter as tk
    from tkinter import messagebox
    from tkinter import filedialog
    from tqdm.contrib.itertools import product
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise


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

    batched=messagebox.askyesno(
        'Batched Operation.',
        'Would you like to apply changes to all .ims files in this folder?'
    )
    filter_width=0.284 # TODO: automatically retrieve voxel size for filter width
    # curr_max=None
    vImage = vImarisApplication.GetImage(0)  
    vNumChannels = vImage.GetSizeC()

    channels=[vImage.GetChannelName(i) for i in range(vNumChannels)]

    root=tk.Tk()
    vars=[]
    
    tk.Label(root,text='Enter the pixel value that will be scaled to maximum intensity for each channel').grid(
        row=0,column=0,columnspan=2,pady=(10,15))
    for i, channel in enumerate(channels,start=1):
        tk.Label(root,text=channel).grid(row=i,column=0,padx=10,pady=5,sticky='w')
        var=tk.StringVar(root,value='255')
        tk.Entry(root,textvariable=var).grid(row=i,column=1,padx=10,pady=5)
        vars.append(var)

    def action():
        try:
            root.curr_max=[float(var.get()) for var in vars]
            for val in root.curr_max:
                assert (val>0. and val<=255.)
            root.quit()
        except (ValueError,AssertionError):
            tk.Label(root,text='Please provide numerical values between 0 and 255 for scaling values.').grid(
                row=len(channels)+2,column=0,columnspan=2,pady=10)

        
    
    tk.Button(root,text='Submit',command=action).grid(row=len(channels)+1,column=0,columnspan=2,pady=10)
    root.mainloop()
    curr_max=root.curr_max
    root.destroy()

    if batched:
        XTBatch(vImarisApplication,ApplyBeautification,(filter_width,curr_max),operate_on_image=False)
    else:
        ApplyBeautification(vImarisApplication,filter_width,curr_max)
        logging.info('Asking user to save image.')
        saved = messagebox.askyesno(
            'Save changes.',
            'Please save or discard changes. Did you save the file?'
        )
        logging.info('User reports that they saved changes: %s', saved)
        logging.info('----- Done Editing %s -----', image_path)
    print('Changes complete.')

def ApplyBeautification(vImarisApplication,filter_width,curr_max):
    vIP = vImarisApplication.GetImageProcessing()
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return
    
    vImage = vImarisApplication.GetImage(0)    
    vNumChannels = vImage.GetSizeC()
    # try: 
    #     l=len(curr_max)
    # if len(curr_max)==vNumChannels:
    #     pass
    # elif len(curr_max)==1:
    #     curr_max=[curr_max]*vNumChannels
    # else:
    #     raise(Exception(''))
    for i in range(vNumChannels):
        # import pdb
        # pdb.set_trace()
        vIP.ContrastStretchChannel(vImage,i,0,curr_max[i],0,255)
        logging.info(f'Stretching channel {i} by casting intensity {curr_max[i]} to maximum')
        vIP.GaussFilterChannel(vImage,i,filter_width)
        logging.info(f'Applying Gaussian filter of width {filter_width} to channel {i}')
    return None


def Beautify(aImarisId):
    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = tk.Tk()
    vRootTkWindow.withdraw()

    try:
        Main(aImarisId)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
