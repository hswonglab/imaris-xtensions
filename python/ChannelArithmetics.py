#  ChannelArithmetics: An Imaris XTension to perform channel arithmetics faster than the matlab extension (hopefully)
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Channel Arithmetics" icon="Python3" tooltip="Performs channel arithmetics similar to the Matlab extension.">
#         <Command>Python3XT::ChannelArithmetics(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ChannelArithmetics allows for the user to perform channel arithmetics. Hopefully this is faster than the matlab implementation

This XTension supports batch operations. The user will be prompted to choose
whether all .ims files in the directory of the current image shall be modified

Note (Amy, 2025-02-02): This function is in development; I've only tested it on addition so far and it seems to work but no guarentees use at your own risk!
Note (Nicole, 2025-05-09): Thanks for the function Amy! Just trying to make it work for boolean expressions (setting clip from 0 to 1 at the end)
Note (Amy, 2025-06-07): I've attempted to add and/or operations, also modified the clip for booleans
Note (Tomer, 2025-06-25): I've merged all the channel arithmetic scripts and did some improvments
'''

#essential dependencies
try:
    import ImarisLib
    import numpy as np

    import tkinter as tk
    from tkinter import simpledialog
    from tkinter import messagebox

    from tqdm import tqdm
    from tqdm.contrib.itertools import product

    import re
    import ast
    import operator
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

# Define allowed operators 
ALLOWED_OPERATORS = {
    ast.Add: (operator.add, "+"),
    ast.Sub: (operator.sub, "-"),
    ast.Mult: (operator.mul, "*"),
    ast.Lt: (np.less, "<"),
    ast.Gt: (np.greater, ">"),
    ast.LtE: (np.less_equal, "<="),
    ast.GtE: (np.greater_equal, ">="),
    ast.Eq: (np.equal, "=="),
    ast.NotEq: (np.not_equal, "!="),
    ast.And: (np.logical_and, "and"),
    ast.Or: (np.logical_or, "or"),
}

# Define allowed functions
ALLOWED_FUNCTIONS = {
    'max': np.maximum,
    'min': np.minimum,
}

def get_formulas_from_user():
    import tkinter.scrolledtext as scrolledtext
    
    # Create a custom dialog for multi-line input
    dialog = tk.Toplevel()
    dialog.title("Channel Arithmetic Formulas")
    dialog.geometry("500x500")
    dialog.transient()
    dialog.grab_set()
    
    # Instructions label
    instructions = tk.Label(dialog, text=f"""Enter channel arithmetic formulas (one per line):

• Allowed operators: {', '.join(op[1] for op in ALLOWED_OPERATORS.values())}
• Allowed functions: {', '.join(ALLOWED_FUNCTIONS.keys())}
• Operands can be channel names (e.g. ch1, ch2, etc.) or numbers
• Each formula will be executed sequentially and the result will be stored in a new channel

Example:
  ch1 + ch2
  ch3 * 2
  ch1 > ch2
  max(ch1, ch2, ch8)""", justify=tk.LEFT, anchor="w")
    instructions.pack(pady=10, padx=10, fill=tk.X)
    
    # Text area for formulas
    text_area = scrolledtext.ScrolledText(dialog, height=10, width=60)
    text_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
    text_area.focus()
    
    # Result variable
    formulas = None
    
    def on_ok():
        nonlocal formulas
        content = text_area.get("1.0", tk.END).strip()
        if content:
            formulas = [line.strip() for line in content.split('\n') if line.strip()]
        dialog.destroy()
    
    def on_cancel():
        dialog.destroy()
    
    # Buttons
    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=10)
    
    ok_button = tk.Button(button_frame, text="OK", command=on_ok, width=10)
    ok_button.pack(side=tk.LEFT, padx=5)
    
    cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel, width=10)
    cancel_button.pack(side=tk.LEFT, padx=5)
    
    # Wait for dialog to close
    dialog.wait_window()
    
    return formulas

def ChannelArithmetics(aImarisId):
    
    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = tk.Tk()
    vRootTkWindow.withdraw()

    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Check if the object is valid
    if vImarisApplication is None:
        messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return
    print(f'Connected to Imaris application (id={aImarisId})')

    # Get Image
    vImage = vImarisApplication.GetImage(0)

    # Get formulas
    formulas = get_formulas_from_user()
    if formulas is None or len(formulas) == 0:
        print("Operation canceled by the user.")
        return

    # Ask for batch
    if batch_enabled:
        batched=messagebox.askyesno(
            'Batched Operation.',
            'Would you like to apply changes to all .ims files in this folder?'
        )
    else:
        batched=False

    if batched: 
        try: 
            XTBatch(vImarisApplication, RunChannelArithmetics, (formulas, True))
        except Exception as e: 
            print(e)
            input("Press enter to exit;")
    else: 
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return
        try: 
            vImageNew = RunChannelArithmetics(vImage, formulas)
            vImarisApplication.SetImage(0, vImageNew)
        except Exception as e: 
            print(e)
            input("Press enter to exit;")

    messagebox.showinfo('Complete', 'The XTension has terminated.')


def RunChannelArithmetics(vImage, formulas, verbose=True): 

    # Start with the original image
    vImageCurrent = vImage.Clone()

    # Process each formula sequentially
    for i, formula_str in enumerate(formulas):
        if verbose:
            print(f"Processing formula {i+1}/{len(formulas)}: {formula_str}")
        
        # Apply the current formula
        vImageCurrent = ApplyFormulaToImage(vImageCurrent, formula_str, verbose)
    
    return vImageCurrent


def ApplyFormulaToImage(vImage, formula_str, verbose=True): 

    # Make a new image 
    vImageNew = vImage.Clone()

    # Get new channel index and name
    ch_out_index = vImage.GetSizeC()
    ch_out_name = formula_str
    if verbose: 
        print(f"Creating channel {ch_out_index + 1}, named {formula_str}")
    vImageNew.SetSizeC(ch_out_index + 1)
    vImageNew.SetChannelName(ch_out_index, ch_out_name)

    # Get channel names and indices, e.g. {"ch3": 2, "ch12": 11}
    channel_indices = {match: int(match[2:]) - 1 for match in re.findall(r'ch\d+', formula_str)}


    # Define a class which can parse arithmetic expressions
    class EvalVisitor(ast.NodeVisitor): 
        
        def visit_BinOp(self, node): 
            left = self.visit(node.left)
            right = self.visit(node.right)
            if type(node.op) in ALLOWED_OPERATORS: 
                return ALLOWED_OPERATORS[type(node.op)][0](left, right)
            else: 
                raise ValueError("Unsupported operator: {}".format(node.op))
        
        def visit_Name(self, node):
            if node.id.startswith("ch") and node.id in channel_values: 
                return np.array(channel_values[node.id])
            raise ValueError("Undefined variable: {}".format(node.id))
        
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id in ALLOWED_FUNCTIONS:
                func = ALLOWED_FUNCTIONS[node.func.id]
                args = [self.visit(arg) for arg in node.args]
                if len(args) < 2:
                    raise ValueError(f"Function {node.func.id} requires at least 2 arguments")
                # For functions like max/min that take multiple arguments, apply iteratively
                result = args[0]
                for arg in args[1:]:
                    result = func(result, arg)
                return result
            else:
                raise ValueError(f"Unsupported function: {node.func.id if isinstance(node.func, ast.Name) else 'unknown'}")
            
        def visit_Compare(self, node):
            left = self.visit(node.left)
            if len(node.ops) != 1 or len(node.comparators) != 1: 
                raise ValueError("Only simple comparisons are supported")
            right = self.visit(node.comparators[0])
            op_type = type(node.ops[0])
            if op_type in ALLOWED_OPERATORS: 
                return ALLOWED_OPERATORS[op_type][0](left, right)
            else: 
                raise ValueError("Undefined variable: {}".format(node.id))
        
        def visit_BoolOp(self, node):
            if len(node.values) != 2: 
                raise ValueError("Can only perform BoolOp with two values")
            values0 = self.visit(node.values[0])
            values1 = self.visit(node.values[1])
            op_type = type(node.op)
            if op_type in ALLOWED_OPERATORS: 
                return ALLOWED_OPERATORS[op_type][0](values0, values1)
            else: 
                raise ValueError("Undefined variable: {}".format(node.id))
        
        def visit_Num(self, node): 
            return np.array(node.n)

        def visit_Constant(self, node): 
            return np.array(node.value)
        
        def visit_Expr(self, node):
            return self.visit(node.value)

    # get channel values
    channel_values = {} # start by initializing an empty dictionary

    ### slice by slice operations originally developed by Eric in LinearUnmixing.py; modified for these purposes here
    #process data slice by slice in square windows of length vWindowSize pixels
    vWindowSize = 10000 # larger windows can speed up execution but will be more memory-intensive
    vNumSlices = vImage.GetSizeZ()
    vXSize = vImage.GetSizeX()
    vYSize=vImage.GetSizeY()

    is_first = True
    warn_clipping_max = True
    warn_clipping_min = True
    for x,y,z in product(range(0,vXSize,vWindowSize),range(0,vYSize,vWindowSize),range(vNumSlices)):
        window_x_len=min(vWindowSize,vXSize-x)
        window_y_len=min(vWindowSize,vYSize-y)

        for ch_name in channel_indices:
            channel_values[ch_name] = np.zeros((window_x_len,window_y_len))
            ch_index = channel_indices[ch_name]
            channel_values[ch_name] = np.array([np.frombuffer(row, dtype=np.uint8) for row in vImage.GetDataSubSliceBytes(aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=ch_index,aIndexT=0,aSizeX=window_x_len,aSizeY=window_y_len)], dtype='int16')

        # parse arithmetic expression
        tree = ast.parse(formula_str, mode='eval')
        if is_first and verbose: 
            print("\n")
            print(ast.dump(ast.parse(formula_str)))
            print("\n")
            is_first = False

        # calculate
        new_channel_values = EvalVisitor().visit(tree.body)

        # Clip values to 0-255 and convert to uint8
        if warn_clipping_max and np.any(new_channel_values > 255):
            print("\nWarning: Some values are above 255, clipping to 255.\n")
            warn_clipping_max = False
        if warn_clipping_min and np.any(new_channel_values < 0):
            print("\nWarning: Some values are below 0, clipping to 0.\n")
            warn_clipping_min = False

        new_channel_values = np.clip(new_channel_values, 0, 255)
        new_channel_values = np.array(new_channel_values, dtype='uint8')
        
        # Add data to new channel in new Image
        vImageNew.SetDataSubSliceBytes(aData=[row.tobytes() for row in new_channel_values],aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=ch_out_index,aIndexT=0)

    return vImageNew
