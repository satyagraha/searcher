###############################################################################
#
#  searcher.py - File search utility 
#
###############################################################################

import fnmatch
import os.path
import re
import sys
import subprocess
import threading
import yaml

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
    def __init__(self, base_dir, recurse, dir_exclusions, file_wildcards, text_pattern, is_case_sensitive, is_regex):
        self._base_dir = os.path.normpath(base_dir)
        self._recurse = recurse
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
        try:
            match = self._text_pattern_regex.search(line)
            return match.start() if match else -1
        except UnicodeDecodeError:
            return -1
    
    def _match_senstitive(self, line):
        try:
            return line.find(self._text_pattern_literal)
        except UnicodeDecodeError:
            return -1
    
    def _match_insensitive(self, line):
        try:
            return line.upper().find(self._text_pattern_literal)
        except UnicodeDecodeError:
            return -1
    
    def is_matching_filename(self, filename):
        return self._matches_wildcards(filename, self._file_wildcards)

    def filter_sub_dirs(self, sub_dirs):
        return [sub_dir for sub_dir in sub_dirs if not self._matches_wildcards(sub_dir, self._dir_exclusions)] if self._recurse else []
    
    def _matches_wildcards(self, name, wildcards):
        return any((fnmatch.fnmatch(name, wildcard) for wildcard in wildcards))

class MatchResult(AttrDict):
    def __init__(self, dir_path, filename, line_no, col_no, line):
        AttrDict.__init__(self)
        self.dir_path = dir_path
        self.filename = filename
        self.file_path = os.path.join(dir_path, filename) if filename else None
        self.line_no = line_no
        self.col_no = col_no
        self.line = line
        
    def as_dir_path(self):
        return MatchResult(self.dir_path, None, None, None, None)
        
    def as_file_path(self):
        return MatchResult(self.dir_path, self.filename, None, None, None)
                
class MatchingThread(threading.Thread):
    
    finished = MatchResult(None, None, None, None, None)
    
    def __init__(self, match_criteria, callback):
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
            # print "sub_dirs", sub_dirs
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
#                 print "filename", filename
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
    
    def __init__(self, etype, eid, value=None):
        wx.PyCommandEvent.__init__(self, etype, eid)
        self._value = value

    def get_value(self):
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
    
    def __init__(self, resource_dir, resource_name):

        # data paths
        yaml_path = os.path.join(resource_dir, resource_name + '.yaml')
        resource_path = os.path.join(resource_dir, resource_name + '.xrc') 
        icon_path = os.path.join(resource_dir, resource_name + '.ico')
      
        # set up configs
        with open(yaml_path) as yaml_stream:
            all_config = AttrDict(yaml.load(yaml_stream))
            os_key = "os." + sys.platform
            platform_config = AttrDict(all_config[os_key])
            print "platform_config", platform_config
            self._common_config = AttrDict(platform_config.common)
            self._activate_config = AttrDict(platform_config.activate)
            self._context_config = AttrDict(platform_config.context)
            self._settings_config = AttrDict(all_config.settings)

        # main frame
        dialog_xrc = xrc.XmlResource(resource_path)
        assert dialog_xrc, 'Failed to create XmlResource: ' + resource_path
        
        root_node_name = 'main_frame'
        main_frame = dialog_xrc.LoadFrame(None, root_node_name)
        assert main_frame, 'Failed to create frame'
        
        self._ui = AttrDict()
        self._load_names(main_frame, dialog_xrc.GetResourceNode(root_node_name))
        
        self._ui.main_frame.SetSize(size=self._settings_config.frame_size)

        self._ui.main_frame.Bind(wx.EVT_CLOSE, self._on_close, id=self._ui.main_frame_id)
        
        ib = wx.IconBundle()
        ib.AddIconFromFile(icon_path, wx.BITMAP_TYPE_ANY)
        self._ui.main_frame.SetIcons(ib)
        
        # options panel
        self._ui.include_files.SetValue(self._settings_config.include_files)
        self._ui.exclude_dirs.SetValue(self._settings_config.exclude_dirs)
        self._ui.text.SetValue("include") ###
        self._ui.match_case.SetValue(self._settings_config.match_case)
        self._ui.regex.SetValue(self._settings_config.regex)
        self._ui.main_frame.Bind(wx.EVT_BUTTON, self._browse, id=self._ui.browse_id)
        self._ui.directory.SetValue(os.path.normpath("D:/development/python")) ###
        self._ui.recurse.SetValue(self._settings_config.recurse)
        
        # control panel
        self._ui.main_frame.Bind(wx.EVT_BUTTON, self._start, id=self._ui.start_id)
        
        self._ui.main_frame.Bind(wx.EVT_BUTTON, self._stop, id=self._ui.stop_id)
        
        self._ui.main_frame.Bind(MatchEvent.event_binding, self._on_Match)
        
        # matches panel
        tree_list_box = wx.BoxSizer(wx.VERTICAL)
        self._ui.tree_list = wx.gizmos.TreeListCtrl(self._ui.tree_list_panel, -1, style=
                                        wx.TR_DEFAULT_STYLE
                                        # | wx.TR_HIDE_ROOT
                                        # | wx.TR_HAS_BUTTONS
                                        # | wx.TR_TWIST_BUTTONS
                                        # | wx.TR_ROW_LINES
                                        # | wx.TR_COLUMN_LINES
                                        # | wx.TR_NO_LINES 
                                        # | wx.TR_HAS_VARIABLE_ROW_HEIGHT
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                   )
        tree_list_box.Add(self._ui.tree_list, 1, wx.EXPAND)
        self._ui.tree_list_panel.SetSizer(tree_list_box)

        isz = (16, 16)
        self._image_list = wx.ImageList(isz[0], isz[1])
        self._fldridx = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, isz))
        self._fldropenidx = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_FILE_OPEN, wx.ART_OTHER, isz))
        self._fileidx = self._image_list.Add(wx.ArtProvider_GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, isz))
        self._ui.tree_list.SetImageList(self._image_list)

        # create some columns
        self._ui.tree_list.AddColumn("Path", flag=wx.COL_RESIZABLE)
        self._ui.tree_list.AddColumn("Text", flag=wx.COL_RESIZABLE)
        self._ui.tree_list.SetMainColumn(0)  # the one with the tree in it...
        self._ui.tree_list.SetColumnWidth(0, self._settings_config.tree_col_size)
        self._ui.tree_list.SetColumnWidth(1, self._settings_config.text_col_size)

        # event handler        
        self._ui.tree_list.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_tree_item_activated)
        self._ui.tree_list.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self._on_tree_item_context_menu)
        
        # matching interface
        self._match_adapter = None
        self._match_data = {}

    def _load_names(self, main_frame, xml_node):
        name = xml_node.GetAttribute("name", "")
        if name:
#             print "name:", name
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
        
    def _browse(self, event):
        dir_dialog = wx.DirDialog(self._ui.main_frame, "Choose a directory:", self._ui.directory.GetValue())
        if dir_dialog.ShowModal() == wx.ID_OK:
            self._ui.directory.SetValue(dir_dialog.GetPath())
        dir_dialog.Destroy()        
        
    def _start(self, event):
        print 'start'
        if self._match_adapter:
            self._match_adapter.stop()
        match_criteria = self._get_match_criteria()
        if not match_criteria:
            return
        self._start_path = match_criteria._base_dir
        self._ui.tree_list.DeleteAllItems()
        self._ui.tree_root = self._ui.tree_list.AddRoot(self._start_path)
        self._matched_dirs = {}
        self._matched_files = {}
#         match_criteria = MatchCriteria(self._start_path, [".git", ".svn"], ["*.py", "*.bat", "*.java"], "Im.*rt", False, True)
        self._match_adapter = MatchAdapter(self._ui.main_frame, match_criteria)
        self._match_adapter.start()
        self._ui.gauge.Pulse()
        
    def _get_match_criteria(self):
        base_dir = self._ui.directory.GetValue().strip()
        if not base_dir:
            return None
        recurse = self._ui.recurse.GetValue()
        dir_exclusions = self._text_to_list(self._ui.exclude_dirs.GetValue())
        file_wildcards = self._text_to_list(self._ui.include_files.GetValue())
        text_pattern = self._ui.text.GetValue().strip()
        is_case_sensitive = self._ui.match_case.GetValue()
        is_regex = self._ui.regex.GetValue()
        return MatchCriteria(base_dir, recurse, dir_exclusions, file_wildcards, text_pattern, is_case_sensitive, is_regex)
        
    def _text_to_list(self, text):
        return [item.strip() for item in text.split(",") if item.strip()]
    
    def _stop(self, event):
        print 'stop'
        if (self._match_adapter):
            self._match_adapter.stop()
            self._match_adapter = None
            self._finished()
        
    def _on_Match(self, evt):
#         print '_on_Match'
        if self._match_adapter:
            match_result = evt.get_value()
#             print match_result.__dict__
            if match_result == MatchingThread.finished:
                self._finished()
            else:
                self._handle_match(match_result)
            
    def _finished(self):
        print '_finished'
        self._ui.gauge.SetValue(0)
        
    def _handle_match(self, match_result):
#         print '_handle_match'
        if match_result.dir_path not in self._matched_dirs:
            self._matched_dirs[match_result.dir_path] = self._add_dir_node(match_result)
        dir_node = self._matched_dirs[match_result.dir_path]
        match_file_key = (match_result.dir_path, match_result.filename)
        if match_file_key not in self._matched_files:
            self._matched_files[match_file_key] = self._add_file_node(dir_node, match_result)
        file_node = self._matched_files[match_file_key]
        if match_result.line_no:
            self._add_line_node(file_node, match_result)
            
    def _add_dir_node(self, match_result):
        first_child = self._ui.tree_list.GetFirstChild(self._ui.tree_root)[0]
        rel_dir_path = os.path.relpath(match_result.dir_path, self._start_path)
        dir_node = self._ui.tree_list.AppendItem(self._ui.tree_root, rel_dir_path)
        self._ui.tree_list.SetItemImage(dir_node, self._fldridx, which=wx.TreeItemIcon_Normal)
        self._ui.tree_list.SetItemImage(dir_node, self._fldropenidx, which=wx.TreeItemIcon_Expanded)
        self._ui.tree_list.SetItemData(dir_node, wx.TreeItemData(match_result.as_dir_path()))
        if not first_child.IsOk():
            self._ui.tree_list.Expand(self._ui.tree_root)
        return dir_node

    def _add_file_node(self, dir_node, match_result):
        first_child = self._ui.tree_list.GetFirstChild(dir_node)[0]
        file_node = self._ui.tree_list.AppendItem(dir_node, match_result.filename)
        self._ui.tree_list.SetItemImage(file_node, self._fileidx, which=wx.TreeItemIcon_Normal)
        self._ui.tree_list.SetItemData(file_node, wx.TreeItemData(match_result.as_file_path()))
        if not first_child.IsOk():
            self._ui.tree_list.Expand(dir_node)
        return file_node
            
    def _add_line_node(self, file_node, match_result):
        first_child = self._ui.tree_list.GetFirstChild(file_node)[0]
        line_node = self._ui.tree_list.AppendItem(file_node, str(match_result.line_no) + ", " + str(match_result.col_no))
#         self._ui.tree_list.SetItemImage(file_node, self._fileidx, which = wx.TreeItemIcon_Normal)
        self._ui.tree_list.SetItemText(line_node, match_result.line, 1)
        self._ui.tree_list.SetItemData(line_node, wx.TreeItemData(match_result))
        if not first_child.IsOk():
            self._ui.tree_list.Expand(file_node)
        return line_node
            
    def _on_tree_item_activated(self, event):
        item = event.GetItem()
        data = self._ui.tree_list.GetItemData(item)
        match_result = data.GetData() if data else None
        print "_on_tree_item_activated", item, data, match_result
        if not match_result:
            return
        template = self._best_config_entry(self._activate_config, match_result)
        self._launch_process(match_result, template)
                
    def _on_tree_item_context_menu(self, event):
        item = event.GetItem()
        data = self._ui.tree_list.GetItemData(item)
        match_result = data.GetData() if data else None
        print "_on_tree_item_context_menu", item, data, match_result
        if not match_result:
            return
        self._ui.popup_menu = wx.Menu()
        menu_defs = self._best_config_entry(self._context_config, match_result)
        for menu_def in menu_defs:
            menu_text, template = menu_def[0], menu_def[1:]
            menu_entry = self._ui.popup_menu.Append(-1, menu_text)
            menu_handler = lambda menu_event, template = template: self._launch_process(match_result, template)
            self._ui.main_frame.Bind(wx.EVT_MENU, menu_handler, menu_entry)
        self._ui.main_frame.PopupMenu(self._ui.popup_menu, event.GetPoint())
        self._ui.popup_menu.Destroy()
                        
    def _best_config_entry(self, config, match_result):
        if match_result.line_no:
            return config.on_line
        elif match_result.file_path:
            return config.on_file_path
        elif match_result.dir_path:
            return config.on_dir_path
        else:
            raise Exception("unexpected: " + str(match_result))

    def _launch_process(self, match_result, template):
        print "template", template
        substitutions = self._common_config.copy()
        substitutions.update(match_result)
        print "substitutions", substitutions
        substituted = [entry.format(**substitutions) for entry in template] 
        print "substituted", substituted
        subprocess.Popen(substituted, close_fds=True, shell=True)
        
###############################################################################

if __name__ == '__main__':
    resource_dir = sys.path[0]
    resource_name = 'searcher'
    app = wx.App(False)
    browser = Searcher(resource_dir, resource_name)
    browser.populate()
    app.MainLoop()

###############################################################################
