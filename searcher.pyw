###############################################################################
#
#  searcher.py - File search utility 
#
###############################################################################

import fnmatch
import os.path
import string
import sys
import threading
import time

import  wx
import  wx.gizmos
from wx import xrc

#----------------------------------------------------------------------
'''
TBD
'''

###############################################################################

class MatchCriteria:
    def __init__(self, base_dir, dir_exclusions, file_wildcards, text_pattern):
        self._base_dir = base_dir
        self._dir_exclusions = dir_exclusions
        self._file_wildcards = file_wildcards
        self._text_pattern = text_pattern

    def is_matching_filename(self, filename):
        return self._matches_wildcards(filename, self._file_wildcards)

    def filter_sub_dirs(self, sub_dirs):
#         print "sub_dirs", sub_dirs
        return [sub_dir for sub_dir in sub_dirs if not self._matches_wildcards(sub_dir, self._dir_exclusions)]
    
    def _matches_wildcards(self, name, wildcards):
#         print "xxx", name, wildcards
        return any((fnmatch.fnmatch(name, wildcard) for wildcard in wildcards))

class MatchResult:
    def __init__(self, dir_path, filename, line_no, line_text):
        self.dir_path = dir_path
        self.filename = filename
        self.line_no = line_no
        self.line_text = line_text
                
class MatchingThread(threading.Thread):
    
    finished = MatchResult(None, None, None, None)
    
    def __init__(self, match_criteria, callback):
        """
        @param parent: The gui object that should recieve the value
        @param value: value to 'calculate' to
        """
        threading.Thread.__init__(self)
        self._match_criteria = match_criteria
        self._callback = callback
        self._running = False

    def run(self):
        """Overrides Thread.run. Don't call this directly its called internally
        when you call Thread.start().
        """
        self._running = True
        for dir_path, sub_dirs, filenames in os.walk(self._match_criteria._base_dir):
            #print "sub_dirs", sub_dirs
            sub_dirs[:] = self._match_criteria.filter_sub_dirs(sub_dirs)
#             // filter filenames
            for filename in filenames:
                if not self._running:
                    self._finished()
                    return
                if not self._match_criteria.is_matching_filename(filename):
                    continue
#                 filepath = os.path.join(dir_path, filename)
                match_result = MatchResult(dir_path, filename, 1, "result")
                self._callback(self, match_result)
#                 time.sleep(0.2)
        self._finished()

    def stop(self):
        print self, "stop"
        self._running = False
        
    def _finished(self):
        self._callback(self, MatchingThread.finished)
        
###############################################################################
            
class MatchEvent(wx.PyCommandEvent):
    
    event_type = wx.NewEventType()
    event_binding = wx.PyEventBinder(event_type, 1)
    
    """Event to signal that a value is ready"""
    def __init__(self, etype, eid, value=None):
        """Creates the event object"""
        wx.PyCommandEvent.__init__(self, etype, eid)
        self._value = value

    def get_value(self):
        """Returns the value from the event.
        @return: the value of this event
        """
        return self._value
    
class MatchAdapter:
    def __init__(self, parent, match_criteria):
        self._parent = parent
        self._match_criteria = match_criteria
        self._matching_thread = None
        
    def start(self):
        if (self._matching_thread):
            raise Exception("already started")
        self._matching_thread = MatchingThread(self._match_criteria, self._handle_match)
        self._matching_thread.start()
        
    def stop(self):
        print self, "stop"
        if (self._matching_thread): 
            self._matching_thread.stop()
            self._matching_thread = None
        
    def _handle_match(self, matching_thread, match_result):
        if self._matching_thread:
            event = MatchEvent(MatchEvent.event_type, -1, match_result)
            wx.PostEvent(self._parent, event)

###############################################################################

class Searcher:
    
    def __init__(self, resource_path, icon_path):
        dialog_xrc = xrc.XmlResource(resource_path)
        assert dialog_xrc, 'Failed to create XmlResource: ' + resource_path
        
        self._match_adapter = None
        self._match_data = {}
        
        self.frame = dialog_xrc.LoadFrame(None, 'MainFrame')
        assert self.frame, 'Failed to create frame'
        self.frame.SetSize(size=(1400, 1000))
#         self.frame.SetClientSize( self.frame.GetBestSize( ) )
        self.frame.Bind(wx.EVT_CLOSE, self._on_close, id=self.frame.GetId())
        
        self._start_c = self._get_control('start')
        self.frame.Bind(wx.EVT_BUTTON, self._start, id=self._start_c.GetId())
        
        self._stop_c = self._get_control('stop')
        self.frame.Bind(wx.EVT_BUTTON, self._stop, id=self._stop_c.GetId())
        
        self._gauge = self._get_control('gauge')
        
#         self.frame.Bind(CountEvent.event_binding, self._on_Count)
        self.frame.Bind(MatchEvent.event_binding, self._on_Match)
        
#         self._matched_splitter = self._get_control('matched_spliter')
#         self._matched_splitter.SetSashPosition(800)
#         
#         self._matched_files = self._get_control('matched_files')
#         self._matched_files.InsertColumn(0, "Name", width=200)
#         self._matched_files.InsertColumn(1, "Location", width=600)
        self._tree_list_panel = self._get_control("tree_list_panel")
#        self._tree_list_panel.SetSize(size=(400, 300))
        tree_list_box = wx.BoxSizer(wx.VERTICAL)

        self._tree_list = wx.gizmos.TreeListCtrl(self._tree_list_panel, -1, style =
                                        wx.TR_DEFAULT_STYLE
                                        #| wx.TR_HIDE_ROOT
                                        #| wx.TR_HAS_BUTTONS
                                        #| wx.TR_TWIST_BUTTONS
                                        #| wx.TR_ROW_LINES
                                        #| wx.TR_COLUMN_LINES
                                        #| wx.TR_NO_LINES 
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                   )
        tree_list_box.Add(self._tree_list, 1, wx.EXPAND)
        
        self._tree_list_panel.SetSizer(tree_list_box)

#         self._tree_list.SetSize(size=(300, 200))

        isz = (16,16)
        self._image_list = wx.ImageList(isz[0], isz[1])
        self._fldridx     = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, isz))
        self._fldropenidx = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_FILE_OPEN,   wx.ART_OTHER, isz))
        self._fileidx     = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, isz))
        self._tree_list.SetImageList(self._image_list)

        # create some columns
        self._tree_list.AddColumn("Path", flag=wx.COL_RESIZABLE)
        self._tree_list.AddColumn("Text", flag=wx.COL_RESIZABLE)
        self._tree_list.SetMainColumn(0) # the one with the tree in it...
        self._tree_list.SetColumnWidth(0, 400)
        
#         self._tree_root = None
#         self._tree_root = self._tree_list.AddRoot("The Root Item")
        
#         self._font_name_c = self._get_control('FontName')
#         self.frame.Bind(wx.EVT_LISTBOX, self._redraw_sample_text, id=self._font_name_c.GetId())
#         
#         self._font_size_c = self._get_control('FontSize')
#         self.frame.Bind(wx.EVT_SPINCTRL, self._redraw_sample_text, id=self._font_size_c.GetId())
#         
#         self._font_weight_c = self._get_control('FontWeight')
#         self.frame.Bind(wx.EVT_CHECKBOX, self._redraw_sample_text, id=self._font_weight_c.GetId())
#         
#         self._font_style_c = self._get_control('FontStyle')
#         self.frame.Bind(wx.EVT_CHECKBOX, self._redraw_sample_text, id=self._font_style_c.GetId())
#         
#         self._font_refresh_c = self._get_control('FontRefresh')
#         self.frame.Bind(wx.EVT_BUTTON, self._refresh_fonts, id=self._font_refresh_c.GetId())
#         
#         self._colour_picker_c = self._get_control('ColourPicker')
#         self.frame.Bind(wx.EVT_COLOURPICKER_CHANGED, self._colour_picked, id=self._colour_picker_c.GetId())
#         
#         self._colour = self._colour_picker_c.GetColour()
#         print "Initial colour:", self._colour
#         
#         self._colour_value_c = self._get_control('ColourValue')
#         self.frame.Bind(wx.EVT_TEXT_ENTER, self._colour_value_changed, id=self._colour_value_c.GetId())
#         
#         self._sample_text_c = self._get_control('SampleText')

        ib = wx.IconBundle()
        ib.AddIconFromFile(icon_path, wx.BITMAP_TYPE_ANY)
        self.frame.SetIcons(ib)

    def _get_control(self, xml_id):
        '''Retrieves the given control (within a dialog) by its xmlid'''
        control = self.frame.FindWindowById(xrc.XRCID(xml_id))
        assert control != None, 'Control not found: ' + xml_id
        return control
    
    def populate(self):
#         self._refresh_fonts(None)
#         self._font_size_c.SetValue(FontBrowser.DEFAULT_FONT_SIZE)
#         
#         sample_text = string.join([chr(i + 32) for i in range(128 - 32)], '')
#         self._sample_text_c.SetValue(sample_text)
#         
#         self._redraw_sample_text(None)
        return

    def _on_close(self, event):
        print "_on_close", event
        self._stop(event)
        self.frame.Destroy()
        
    def _start(self, event):
        print 'start'
        if self._match_adapter:
            self._match_adapter.stop()
        self._start_path = os.path.normpath("D:/development/python")
        self._tree_list.DeleteAllItems()
        self._tree_root = self._tree_list.AddRoot(self._start_path)
        self._matched_dirs = {}
        self._matched_files = {}
        match_criteria = MatchCriteria(self._start_path, [".git", ".svn"], ["*.py", "*.bat", "*.java"], "fred")
        self._match_adapter = MatchAdapter(self.frame, match_criteria)
        self._match_adapter.start()
        self._gauge.Pulse()
        
    def _stop(self, event):
        print 'stop'
        if (self._match_adapter):
            self._match_adapter.stop()
            self._match_adapter = None
            self._finished()
        
    def _on_Match(self, evt):
        print '_on_Match'
        if self._match_adapter:
            match_result = evt.get_value()
            print match_result.__dict__
            if match_result == MatchingThread.finished:
                self._finished()
            else:
                self._handle_match(match_result)
            
    def _finished(self):
        print '_finished'
        self._gauge.SetValue(0)
        
    def _handle_match(self, match_result):
        print '_handle_match'
        if match_result.dir_path not in self._matched_dirs:
            self._matched_dirs[match_result.dir_path] = self._add_dir_node(match_result.dir_path)
        dir_node = self._matched_dirs[match_result.dir_path]
        match_file_key = (match_result.dir_path, match_result.filename)
        if match_file_key not in self._matched_files:
            self._matched_files[match_file_key] = self._add_file_node(dir_node, match_file_key)
            
    def _add_dir_node(self, dir_path):
        first_child = self._tree_list.GetFirstChild(self._tree_root)[0]
        rel_dir_path = os.path.relpath(dir_path, self._start_path)
        dir_node = self._tree_list.AppendItem(self._tree_root, rel_dir_path)
        self._tree_list.SetItemImage(dir_node, self._fldridx, which = wx.TreeItemIcon_Normal)
        self._tree_list.SetItemImage(dir_node, self._fldropenidx, which = wx.TreeItemIcon_Expanded)
        if not first_child.IsOk():
            self._tree_list.Expand(self._tree_root)
        return dir_node

    def _add_file_node(self, dir_node, (dir_path, filename)):
        first_child = self._tree_list.GetFirstChild(dir_node)[0]
        file_node = self._tree_list.AppendItem(dir_node, filename)
        self._tree_list.SetItemImage(file_node, self._fileidx, which = wx.TreeItemIcon_Normal)
        if not first_child.IsOk():
            self._tree_list.Expand(dir_node)
        return file_node
            
    
###############################################################################

def runAppXRC(resource_dir, resource_name):
    resource_path = os.path.join(resource_dir, resource_name + '.xrc') 
    icon_path = os.path.join(resource_dir, resource_name + '.ico')
    app = wx.App(False)
    browser = Searcher(resource_path, icon_path)
    browser.populate()
    browser.frame.Show()
    app.MainLoop()
    return

###############################################################################

if __name__ == '__main__':
    resource_dir = sys.path[0]
    resource_name = 'searcher'
    runAppXRC(resource_dir, resource_name)

###############################################################################
