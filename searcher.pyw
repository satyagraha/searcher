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
import time
import traceback
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
        return [sub_dir for sub_dir in sub_dirs
                 if not self._matches_wildcards(sub_dir, self._dir_exclusions)] if self._recurse else []
    
    def _matches_wildcards(self, name, wildcards):
        return any((fnmatch.fnmatch(name, wildcard) for wildcard in wildcards))

###############################################################################

class MatchBase(AttrDict):
    def __init__(self):
        AttrDict.__init__(self)

class MatchStatus(MatchBase):
    def __init__(self):
        MatchBase.__init__(self)

class MatchStatusDir(MatchStatus):
    def __init__(self, dir_path):
        MatchStatus.__init__(self)
        self.dir_path = dir_path

class MatchStatusFoundCount(MatchStatus):
    def __init__(self, found_count):
        MatchStatus.__init__(self)
        self.found_count = found_count

class MatchStatusElapsedTime(MatchStatus):
    def __init__(self, elapsed_time):
        MatchStatus.__init__(self)
        self.elapsed_time = elapsed_time

class MatchStatusException(MatchStatus):
    def __init__(self, ex):
        MatchStatus.__init__(self)
        self.ex = ex 
        self.message = traceback.format_exc()

class MatchStatusEnd(MatchStatus):
    def __init__(self):
        MatchStatus.__init__(self)

class MatchResult(MatchBase):
    def __init__(self):
        MatchBase.__init__(self)
    
class MatchResultDir(MatchResult):
    def __init__(self, dir_path):
        MatchResult.__init__(self)
        self.dir_path = dir_path
        
    def as_dir_path(self):
        return MatchResultDir(self.dir_path)
        
class MatchResultFile(MatchResultDir):
    def __init__(self, dir_path, filename):
        MatchResultDir.__init__(self, dir_path)
        self.filename = filename
        self.file_path = os.path.join(dir_path, filename)

    def as_file_path(self):
        return MatchResultFile(self.dir_path, self.filename)
    
class MatchResultLine(MatchResultFile):
    def __init__(self, dir_path, filename, line_no, col_no, line):
        MatchResultFile.__init__(self, dir_path, filename)
        self.line_no = line_no
        self.col_no = col_no
        self.line = line

###############################################################################
                
class MatchingThread(threading.Thread):
    
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
        self._started_at = time.time()
        try:
            self._search()
        except Exception as ex:
            self._exception(ex)
        finally:
            self._send_elapsed()
            self._finished()

    def _search(self):
        found_count = 0
        for dir_path, sub_dirs, filenames in os.walk(self._match_criteria._base_dir):
            dir_status = MatchStatusDir(dir_path)
            self._callback(self, dir_status)
            self._send_found_count(found_count)
            self._send_elapsed()
            # print "sub_dirs", sub_dirs
            sub_dirs[:] = self._match_criteria.filter_sub_dirs(sub_dirs)
            for filename in filenames:
                if not self._running:
                    return
                if not self._match_criteria.is_matching_filename(filename):
                    continue
                if not self._match_criteria.text_pattern:
                    found_count += 1
                    match_result = MatchResultFile(dir_path, filename)
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
                        found_count += 1
                        match_result = MatchResultLine(dir_path, filename, line_no, col_no, line)
                        self._callback(self, match_result)
        self._send_found_count(found_count)

    def _send_found_count(self, found_count):
        found_count_status = MatchStatusFoundCount(found_count)
        self._callback(self, found_count_status)
                
    def _send_elapsed(self):
        elapsed_time = time.time() - self._started_at
        elapsed_time_status = MatchStatusElapsedTime(elapsed_time)
        self._callback(self, elapsed_time_status)
                
    def stop(self):
        print self, "stop"
        self._running = False
        
    def _exception(self, ex):
        match_ex = MatchStatusException(ex)
        self._callback(self, match_ex)
    
    def _finished(self):
        match_end = MatchStatusEnd()
        self._callback(self, match_end)
        
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
        yaml_dirs = [os.path.expanduser("~"), resource_dir] 
        resource_path = os.path.join(resource_dir, resource_name + '.xrc') 
        icon_path = os.path.join(resource_dir, resource_name + '.ico')
      
        # set up configs
        for yaml_dir in yaml_dirs:
            yaml_path = os.path.join(yaml_dir, resource_name + '.yaml')
            if os.access(yaml_path, os.R_OK):
                with open(yaml_path) as yaml_stream:
                    all_config = AttrDict(yaml.load(yaml_stream))
                    os_key = "os." + sys.platform
                    platform_config = AttrDict(all_config[os_key])
                    print "platform_config", platform_config
                    self._common_config = AttrDict(platform_config.common)
                    self._activate_config = AttrDict(platform_config.activate)
                    self._context_config = AttrDict(platform_config.context)
                    self._settings_config = AttrDict(all_config.settings)
                break

        # main frame
        dialog_xrc = xrc.XmlResource(resource_path)
        assert dialog_xrc, 'Failed to create XmlResource: ' + resource_path
        
        root_node_name = 'main_frame'
        main_frame = dialog_xrc.LoadFrame(None, root_node_name)
        assert main_frame, 'Failed to create frame'
        
        self._ui = AttrDict()
        self._load_names(main_frame, dialog_xrc.GetResourceNode(root_node_name))
        self._bind_accelerators()
        
        self._ui.main_frame.SetSize(size=self._settings_config.frame_size)

        self._ui.main_frame.Bind(wx.EVT_CLOSE, self._on_close)
        
        ib = wx.IconBundle()
        ib.AddIconFromFile(icon_path, wx.BITMAP_TYPE_ANY)
        self._ui.main_frame.SetIcons(ib)
        
        # options panel
        self._ui.include_files.SetValue(self._settings_config.include_files)
        self._ui.exclude_dirs.SetValue(self._settings_config.exclude_dirs)
        self._ui.text.SetValue("include")  # ##
        self._ui.match_case.SetValue(self._settings_config.match_case)
        self._ui.regex.SetValue(self._settings_config.regex)
        self._ui.main_frame.Bind(wx.EVT_BUTTON, self._browse, id=self._ui.browse_id)
        self._ui.directory.SetValue(os.path.normpath("D:/development/python"))  # ##
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
        self._ui.tree_list.Bind(wx.EVT_CONTEXT_MENU, self._on_tree_item_context_menu)
        self._ui.tree_list.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self._on_tree_item_right_click)
        
        # status bar
        self._ui.gauge = wx.Gauge(self._ui.status_bar)
        self._ui.status_bar.SetFieldsCount(3)
        self._ui.status_bar.SetStatusWidths([-2, -1, -1])
        self._ui.status_bar.Bind(wx.EVT_SIZE, self._on_size_status_bar)
        
        # matching interface
        self._match_adapter = None
        self._match_data = {}

    def _load_names(self, main_frame, xml_node):
        name = xml_node.GetAttribute("name", "")
        if name and not name.startswith("_"):
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
            
    def _bind_accelerators(self):
#         return
        accelerators = []
        def add_accelerator(acc_mod, acc_key, acc_handler):
            acc_id = wx.NewId()
            accelerators.append((acc_mod, acc_key, acc_id))
            self._ui.main_frame.Bind(wx.EVT_MENU, acc_handler, None, acc_id)
            
        label_suffix = "_label"
        acc_patt = re.compile(r'&([a-z])', re.IGNORECASE)
        for label_name in self._ui.keys():
            if label_name.endswith(label_suffix):
                label = self._ui[label_name]
                label_text = label.GetLabel()
                control_name = label_name[:-len(label_suffix)]
                control = self._ui[control_name]
#                 print control_name
                acc_match = acc_patt.search(label_text)
                if acc_match:
                    acc_letter = acc_match.group(1).upper()
                    acc_handler = lambda event, control = control: self._accel_handler(event, control)
                    add_accelerator(wx.ACCEL_ALT, ord(acc_letter), acc_handler) 
        add_accelerator(wx.ACCEL_ALT, ord("A"), lambda event: self._accel_handler(event, self._ui.start))
        add_accelerator(wx.ACCEL_ALT, ord("O"), lambda event: self._accel_handler(event, self._ui.stop))
        add_accelerator(wx.ACCEL_ALT, ord("M"), lambda event: self._accel_handler(event, self._ui.tree_list))
        add_accelerator(wx.ACCEL_ALT, wx.WXK_RETURN, self._start)
        add_accelerator(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, self._stop)
        self._ui.main_frame.SetAcceleratorTable(wx.AcceleratorTable(accelerators))
            
    def _accel_handler(self, event, control):
        print event
        control.SetFocus()
            
    def populate(self):
        self._ui.main_frame.Show()
        self._ui.menu_bar = self._ui.main_frame.GetMenuBar()
#         print "menus", self._ui.menu_bar.GetMenus() 
        for (menu, title) in self._ui.menu_bar.GetMenus():
            for menu_item in menu.GetMenuItems():
#                 print "menu_item", menu_item.GetItemLabelText()
                menu_key = "menu_" + menu_item.GetItemLabelText().strip(".").lower()
                self._ui[menu_key] = menu_item
        self._ui.main_frame.Bind(wx.EVT_MENU, self._on_close, self._ui.menu_exit) 
        self._ui.main_frame.Bind(wx.EVT_MENU, self._on_about, self._ui.menu_about)
        if len(sys.argv) > 1:
            self._ui.directory.SetValue(sys.argv[1]) 

    def _on_size_status_bar(self, event):
#         print "_on_size_status_bar", event
        status_bar_size = self._ui.status_bar.GetSize()
        gauge_width = 200
        gauge_border = 2
        gauge_pos = wx.Point(status_bar_size.GetWidth() - gauge_width - gauge_border, gauge_border)
        gauge_size = wx.Size(gauge_width, status_bar_size.GetHeight() - 2 * gauge_border)
        self._ui.gauge.SetSize(gauge_size)
        self._ui.gauge.SetPosition(gauge_pos)
        
    def _on_close(self, event):
        print "_on_close", event
        self._stop(event)
        self._ui.main_frame.Destroy()
        
    def _on_about(self, event):
        message = "Version: " + self._settings_config.version
        message_dialog = wx.MessageDialog(self._ui.main_frame, message, "About")
        message_dialog.ShowModal()
        message_dialog.Destroy()
        
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
            if isinstance(match_result, MatchStatusDir):
                self._handle_status_dir(match_result)
            elif isinstance(match_result, MatchStatusFoundCount):
                self._handle_status_found_count(match_result)
            elif isinstance(match_result, MatchStatusElapsedTime):
                self._handle_status_elapsed_time(match_result)
            elif isinstance(match_result, MatchStatusEnd):
                self._finished()
            elif isinstance(match_result, MatchStatusException):
                self._handle_exception(match_result)
            else:
                self._handle_match(match_result)
            
    def _handle_status_dir(self, status_dir):
        message = "Searching: " + status_dir.dir_path
        self._ui.status_bar.SetStatusText(message, 0)
        
    def _handle_status_found_count(self, status_found_count):
        message = "Found: " + str(status_found_count.found_count)
        self._ui.status_bar.SetStatusText(message, 1)
        
    def _handle_status_elapsed_time(self, status_elapsed_time):
        message = "Elapsed: " + ("%.1f" % status_elapsed_time.elapsed_time) + "s"
        self._ui.status_bar.SetStatusText(message, 2)
        
    def _handle_exception(self, match_ex):
#         print '_handle_exception', match_ex
        message_dialog = wx.MessageDialog(self._ui.main_frame, match_ex.message, "Exception", wx.ICON_ERROR)
        message_dialog.ShowModal()
        message_dialog.Destroy()
        
    def _finished(self):
#         print '_finished'
        self._ui.gauge.SetValue(0)
        
    def _handle_match(self, match_result):
#         print '_handle_match'
        if match_result.dir_path not in self._matched_dirs:
            self._matched_dirs[match_result.dir_path] = self._add_dir_node(match_result)
        dir_node = self._matched_dirs[match_result.dir_path]
        match_file_key = (match_result.dir_path, match_result.filename)
        if match_file_key not in self._matched_files:
            self._matched_files[match_file_key] = self._add_file_node(dir_node, match_result)
        if isinstance(match_result, MatchResultLine):
            file_node = self._matched_files[match_file_key]
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
        item = self._ui.tree_list.GetSelection()
        if not item.IsOk():
            return
        (tree_x, tree_y) = self._ui.tree_list.GetPositionTuple()
        (item_x, item_y, item_w, item_d) = self._ui.tree_list.GetBoundingRect(item)
        position = wx.Point(tree_x + item_x, tree_y + item_y)
        self._show_tree_item_context_menu(item, position)

    def _on_tree_item_right_click(self, event):
        item = event.GetItem()
        if not item.IsOk():
            return
        position = event.GetPoint()
        self._show_tree_item_context_menu(item, position)
        
    def _show_tree_item_context_menu(self, item, position):
        data = self._ui.tree_list.GetItemData(item)
        match_result = data.GetData() if data else None
#         print "_on_tree_item_context_menu", item, data, match_result
        if not match_result:
            return
        self._ui.popup_menu = wx.Menu()
        menu_defs = self._best_config_entry(self._context_config, match_result)
        for menu_def in menu_defs:
            menu_text, template = menu_def[0], menu_def[1:]
            menu_entry = self._ui.popup_menu.Append(-1, menu_text)
            menu_handler = lambda menu_event, template = template: self._handle_context(match_result, template)
            self._ui.main_frame.Bind(wx.EVT_MENU, menu_handler, menu_entry)
        self._ui.main_frame.PopupMenu(self._ui.popup_menu, position)
        self._ui.popup_menu.Destroy()
                        
    def _best_config_entry(self, config, match_result):
        if isinstance(match_result, MatchResultLine):
            return config.on_line
        elif isinstance(match_result, MatchResultFile):
            return config.on_file_path
        elif isinstance(match_result, MatchResultDir):
            return config.on_dir_path
        else:
            raise Exception("unexpected: " + str(match_result))

    def _handle_context(self, match_result, template):
        if template == ["copy_dir_path"]:
            self._copy_path(match_result.dir_path)
        elif template == ["copy_file_path"]:
            self._copy_path(match_result.file_path)
        else:
            self._launch_process(match_result, template)
            
    def _copy_path(self, path):
        clip_data = wx.TextDataObject()
        clip_data.SetText(path)
        wx.TheClipboard.Open()
        wx.TheClipboard.SetData(clip_data)
        wx.TheClipboard.Close()
        
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
