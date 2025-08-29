from typing import List, Optional

import tkinter

class MessageBox(object):
    '''A helper class for creating custom Tkinter dialog boxes.'''

    def __init__(self, title, msg, options, entry=False):
        root = self.root = tkinter.Tk()
        root.title(title)
        self.result = None
        
        # Create main frame for the window.
        main = tkinter.Frame(root)
        main.pack(ipadx=2, ipady=2)
        message = tkinter.Label(main, text=msg)
        message.pack(padx=8, pady=8)
        
        # If an entry field was requested, create it and focus on it.
        if entry:
            self.entry = tkinter.Entry(main)
            self.entry.pack()
            self.entry.focus_set()
        
        # Create frame for buttons.
        buttons_frame = tkinter.Frame(main)
        buttons_frame.pack(padx=4, pady=4)

        # Create buttons.
        for i, option in enumerate(options):
            btn = tkinter.Button(buttons_frame, width=len(option), text=option)
            btn['command'] = lambda x=option: self.handler(x)
            btn.pack(side='left')
            btn.bind('<KeyPress-Return>', func=btn['command'])
            if i == 0 and not entry:
                btn.focus_set()

    def handler(self, option):
        self.result = option
        self.root.quit()


def flexible_mbox(title: str, msg: str, options: List[str]) -> Optional[str]:
    '''Create a dialog box for user selection and return the result.

    Arguments:
        title: Title for the dialog window.
        msg: Message to display in the body of the window.
        options: List of button labels. One button will be displayed per entry.
            When the user clicks a button, the dialog window will close, and
            the selected button's label will be returned.

    Returns:
        Label of the button selected by the user, or None if the user closes
        the dialog without clicking a button.
    '''
    msgbox = MessageBox(title, msg, options)
    msgbox.root.mainloop()
    msgbox.root.destroy()
    return msgbox.result


if __name__ == '__main__':
    print(flexible_mbox('title!', 'testing', ['Red', 'Green', 'Blue']))
