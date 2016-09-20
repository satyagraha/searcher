###############################################################################
#
#  searcher.py - File search utility 
#
###############################################################################

import fnmatch
import os.path
import re
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

class AttrDict(dict):
    def __init__(self, *a, **kw):
        dict.__init__(self, *a, **kw)
        self.__dict__ = self

###############################################################################

class MatchCriteria:
    def __init__(self, base_dir, dir_exclusions, file_wildcards, text_pattern, is_case_sensitive, is_regex):
        self._base_dir = base_dir
        self._dir_exclusions = dir_exclusions
        self._file_wildcards = file_wildcards
        self.text_pattern = text_pattern
        # set up self.matches(line) which returns col_no on match, otherwise -1
        if is_regex:
            flags = 0 if is_case_sensitive else re.IGNORECASE
            self._text_pattern_regex = re.compile(text_pattern, flags)
            self.matches = self._match_regex
        else:
            self._text_pattern_literal = text_pattern if is_case_sensitive else text_pattern.upper() 
            self.matches = self._match_senstitive if is_case_sensitive else self._match_insensitive

    def _match_regex(self, line):
        match = self._text_pattern_regex.search(line)
        return match.start() if match else -1
    
    def _match_senstitive(self, line):
        return line.find(self._text_pattern_literal)
    
    def _match_insensitive(self, line):
        return line.upper().find(self._text_pattern_literal)
    
    def is_matching_filename(self, filename):
        return self._matches_wildcards(filename, self._file_wildcards)

    def filter_sub_dirs(self, sub_dirs):
#         print "sub_dirs", sub_dirs
        return [sub_dir for sub_dir in sub_dirs if not self._matches_wildcards(sub_dir, self._dir_exclusions)]
    
    def _matches_wildcards(self, name, wildcards):
#         print "xxx", name, wildcards
        return any((fnmatch.fnmatch(name, wildcard) for wildcard in wildcards))

class MatchResult:
    def __init__(self, dir_path, filename, line_no, col_no, line):
        self.dir_path = dir_path
        self.filename = filename
        self.line_no = line_no
        self.col_no = col_no
        self.line = line
                
class MatchingThread(threading.Thread):
    
    finished = MatchResult(None, None, None, None, None)
    
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
        self._search()
        self._finished()

    def _search(self):
        for dir_path, sub_dirs, filenames in os.walk(self._match_criteria._base_dir):
            #print "sub_dirs", sub_dirs
            sub_dirs[:] = self._match_criteria.filter_sub_dirs(sub_dirs)
            for filename in filenames:
                if not self._running:
                    return
                if not self._match_criteria.is_matching_filename(filename):
                    continue
                if self._match_criteria.text_pattern is None:
                    match_result = MatchResult(dir_path, filename, None, None)
                    self._callback(self, match_result)
                    continue
                line_no = 0
                for line in file(os.path.join(dir_path, filename)):
                    if not self._running:
                        return
                    line_no += 1
                    col_no = self._match_criteria.matches(line)
                    if col_no != -1:
                        match_result = MatchResult(dir_path, filename, line_no, col_no, line)
                        self._callback(self, match_result)
        
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
        
        root_node_name = 'main_frame'
        main_frame = dialog_xrc.LoadFrame(None, root_node_name)
        assert main_frame, 'Failed to create frame'
        
        self._ui = AttrDict()
        self._load_names(main_frame, dialog_xrc.GetResourceNode(root_node_name))
        
        self._ui.main_frame.SetSize(size=(1400, 1000))

        self._ui.main_frame.Bind(wx.EVT_CLOSE, self._on_close, id=self._ui.main_frame_id)
        
        self._ui.main_frame.Bind(wx.EVT_BUTTON, self._start, id=self._ui.start_id)
        
        self._ui.main_frame.Bind(wx.EVT_BUTTON, self._stop, id=self._ui.stop_id)
        
        self._ui.main_frame.Bind(MatchEvent.event_binding, self._on_Match)
        
        tree_list_box = wx.BoxSizer(wx.VERTICAL)
        self._ui.tree_list = wx.gizmos.TreeListCtrl(self._ui.tree_list_panel, -1, style =
                                        wx.TR_DEFAULT_STYLE
                                        #| wx.TR_HIDE_ROOT
                                        #| wx.TR_HAS_BUTTONS
                                        #| wx.TR_TWIST_BUTTONS
                                        #| wx.TR_ROW_LINES
                                        #| wx.TR_COLUMN_LINES
                                        #| wx.TR_NO_LINES 
                                        #| wx.TR_HAS_VARIABLE_ROW_HEIGHT
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                   )
        tree_list_box.Add(self._ui.tree_list, 1, wx.EXPAND)
        self._ui.tree_list_panel.SetSizer(tree_list_box)

        isz = (16,16)
        self._image_list = wx.ImageList(isz[0], isz[1])
        self._fldridx     = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, isz))
        self._fldropenidx = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_FILE_OPEN,   wx.ART_OTHER, isz))
        self._fileidx     = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, isz))
        self._ui.tree_list.SetImageList(self._image_list)

        # create some columns
        self._ui.tree_list.AddColumn("Path", flag=wx.COL_RESIZABLE)
        self._ui.tree_list.AddColumn("Text", flag=wx.COL_RESIZABLE)
        self._ui.tree_list.SetMainColumn(0) # the one with the tree in it...
        self._ui.tree_list.SetColumnWidth(0, 400)

        # event handler        
        self._ui.tree_list.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_tree_item_activated)
        
        ib = wx.IconBundle()
        ib.AddIconFromFile(icon_path, wx.BITMAP_TYPE_ANY)
        self._ui.main_frame.SetIcons(ib)

    def _load_names(self, main_frame, xml_node):
        name = xml_node.GetAttribute("name", "")
        if name:
            print "name:", name
            xrc_id = xrc.XRCID(name)
            control = main_frame.FindWindowById(xrc_id)
            assert control != None, 'Control not found: ' + name
            self._ui[name] = control
            self._ui[name + "_id"] = xrc_id
        child = xml_node.GetChildren()
        while child: 
            self._load_names(main_frame, child)
            child = child.GetNext()
            
    def populate(self):
        self._ui.main_frame.Show()

    def _on_close(self, event):
        print "_on_close", event
        self._stop(event)
        self._ui.main_frame.Destroy()
        
    def _start(self, event):
        print 'start'
        if self._match_adapter:
            self._match_adapter.stop()
        self._start_path = os.path.normpath("D:/development/python")
        self._ui.tree_list.DeleteAllItems()
        self._ui.tree_root = self._ui.tree_list.AddRoot(self._start_path)
        self._matched_dirs = {}
        self._matched_files = {}
        match_criteria = MatchCriteria(self._start_path, [".git", ".svn"], ["*.py", "*.bat", "*.java"], "Import", True, True)
        self._match_adapter = MatchAdapter(self._ui.main_frame, match_criteria)
        self._match_adapter.start()
        self._ui.gauge.Pulse()
        
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
        self._ui.gauge.SetValue(0)
        
    def _handle_match(self, match_result):
        print '_handle_match'
        if match_result.dir_path not in self._matched_dirs:
            self._matched_dirs[match_result.dir_path] = self._add_dir_node(match_result.dir_path)
        dir_node = self._matched_dirs[match_result.dir_path]
        match_file_key = (match_result.dir_path, match_result.filename)
        if match_file_key not in self._matched_files:
            self._matched_files[match_file_key] = self._add_file_node(dir_node, match_file_key)
        file_node = self._matched_files[match_file_key]
        if match_result.line_no:
            self._add_line_node(file_node, match_result.line_no, match_result.col_no, match_result.line)
            
    def _add_dir_node(self, dir_path):
        first_child = self._ui.tree_list.GetFirstChild(self._ui.tree_root)[0]
        rel_dir_path = os.path.relpath(dir_path, self._start_path)
        dir_node = self._ui.tree_list.AppendItem(self._ui.tree_root, rel_dir_path)
        self._ui.tree_list.SetItemImage(dir_node, self._fldridx, which = wx.TreeItemIcon_Normal)
        self._ui.tree_list.SetItemImage(dir_node, self._fldropenidx, which = wx.TreeItemIcon_Expanded)
        if not first_child.IsOk():
            self._ui.tree_list.Expand(self._ui.tree_root)
        return dir_node

    def _add_file_node(self, dir_node, (dir_path, filename)):
        first_child = self._ui.tree_list.GetFirstChild(dir_node)[0]
        file_node = self._ui.tree_list.AppendItem(dir_node, filename)
        self._ui.tree_list.SetItemImage(file_node, self._fileidx, which = wx.TreeItemIcon_Normal)
        if not first_child.IsOk():
            self._ui.tree_list.Expand(dir_node)
        return file_node
            
    def _add_line_node(self, file_node, line_no, col_no, line):
        first_child = self._ui.tree_list.GetFirstChild(file_node)[0]
        line_node = self._ui.tree_list.AppendItem(file_node, str(line_no) + ", " + str(col_no))
#         self._ui.tree_list.SetItemImage(file_node, self._fileidx, which = wx.TreeItemIcon_Normal)
        self._ui.tree_list.SetItemText(line_node, line, 1)
        if not first_child.IsOk():
            self._ui.tree_list.Expand(file_node)
        return line_node
            
    def _on_tree_item_activated(self, event):
        item = event.GetItem()
        print "_on_tree_item_activated", item
        
###############################################################################

def runAppXRC(resource_dir, resource_name):
    resource_path = os.path.join(resource_dir, resource_name + '.xrc') 
    icon_path = os.path.join(resource_dir, resource_name + '.ico')
    app = wx.App(False)
    browser = Searcher(resource_path, icon_path)
    browser.populate()
    app.MainLoop()
    return

###############################################################################

if __name__ == '__main__':
    resource_dir = sys.path[0]
    resource_name = 'searcher'
    runAppXRC(resource_dir, resource_name)

###############################################################################
