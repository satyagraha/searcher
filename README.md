# searcher - GUI file search utility 
This project provides a simple portable GUI-based file search utility. Written in Python 
and using the wxPython GUI toolkit, it runs on most modern operating systems. While not necessarily
as fast as complex multithreaded search tools, it is reasonably performant and very customizable. 

![capture](screenshot.png)

## Requirements
The application requires the following software components, and is known to work with the shown versions but may run with earlier ones:
- [Python](http://www.python.org) - 2.7.12
- [wxPython](https://wxpython.org/) - 3.0.2.0
- [PyYAML](http://pyyaml.org/) - 3.12

## Get Started
Clone this repository in the usual way. Execute the file `searcher.pyw` with the UI-based Python interpreter, e.g. `pythonw.exe` on Windows.

## Usage
Use the dialog at the top of the UI to navigate to a folder to search, set a file pattern, set a search text value, and then
press the _Start_ button to commence searching.

Assuming matches are found, they appear in a tree view with three types of entry. Directories are the first type, and have children which are files,
and the files have children which are line matches.

In the results tree, you can select a row and then press _Enter_ to perform the default action for that type of entry,
typically opening the file in your preferred editor.

Similarly, on a results tree row you can click the right-hand mouse button to activate the context (pop-up) menu for that type of entry;
then press _Enter_ for the selected action.

When started from the command line, the program accepts an optional initial directory path argument.

### Windows Explorer Context Menu
It is quite easy to add a Windows Explorer context menu entry to launch the searcher program for a particular directory, as follows:
- Open Windows Explorer and type `shell:sendto` into the address bar; this will open the _SendTo_ folder for your system
- Activate the context menu in that folder (right-click) and select _New_ => _Shortcut_
- In the _Create Shortcut_ wizard dialog, click _Browse_ and navigate to and select the `searcher.pyw` file
- Proceed through the rest of the wizard in the usual way
Now, on any folder shown in Windows Explorer you can activate the context menu, select _Send To_ for the new entry to start the searcher
program with that folder as the pre-selected search directory.

The above assumes a default Windows Python installation which has associated the `.pyw` file extension with the main Python interpreter executable;
otherwise just specify the path to the interpreter followed by the path to the searcher source code. 

## Configuration
The application is configured via the file `searcher.yaml` which is a simple [YAML](https://en.wikipedia.org/wiki/YAML) file.
It is organized into sections by operating system, and entries can be customized for user preferences as described therein.

## Development
Note the UI is defined in `searcher.xrc` which is edited with the visual UI tool [XRCEd](https://wiki.wxpython.org/XRCed)
which is part of the standard wx distribution in package `wx.tools.XRCed.xrced`.

## To Do
- Match for filename only
- Keyboard accelerators 
- Tabbing behaviour
- Better icon
- Status bar content

## History
1.0.0 Initial version
