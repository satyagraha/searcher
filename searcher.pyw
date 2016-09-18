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
from wx import xrc

#----------------------------------------------------------------------
'''
TBD
'''

###############################################################################

class CountEvent(wx.PyCommandEvent):
    
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
    
class CountingThread(threading.Thread):
    def __init__(self, parent, value):
        """
        @param parent: The gui object that should recieve the value
        @param value: value to 'calculate' to
        """
        threading.Thread.__init__(self)
        self._parent = parent
        self._value = value

    def run(self):
        """Overrides Thread.run. Don't call this directly its called internally
        when you call Thread.start().
        """
        time.sleep(5) # our simulated calculation time
        evt = CountEvent(CountEvent.event_type, -1, self._value)
        wx.PostEvent(self._parent, evt)

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
                    return
                if not self._match_criteria.is_matching_filename(filename):
                    continue
#                 filepath = os.path.join(dir_path, filename)
                match_result = MatchResult(dir_path, filename, 1, "result")
                self._callback(self, match_result)
                time.sleep(0.1)

    def stop(self):
        print self, "stop"
        self._running = False
        
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

class OldMatchingThread(threading.Thread):
    def __init__(self, parent, value):
        """
        @param parent: The gui object that should recieve the value
        @param value: value to 'calculate' to
        """
        threading.Thread.__init__(self)
        self._parent = parent
        self._value = value

    def run(self):
        """Overrides Thread.run. Don't call this directly its called internally
        when you call Thread.start().
        """
        time.sleep(5) # our simulated calculation time
        evt = CountEvent(CountEvent.event_type, -1, self._value)
        wx.PostEvent(self._parent, evt)
            
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
        
        self._matched_splitter = self._get_control('matched_spliter')
        self._matched_splitter.SetSashPosition(800)
        
        self._matched_files = self._get_control('matched_files')
        self._matched_files.InsertColumn(0, "Name", width=200)
        self._matched_files.InsertColumn(1, "Location", width=600)
        
        
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
#         worker = CountingThread(self.frame, 99)
#         worker.start()
        self._match_data = {}
        match_criteria = MatchCriteria("D:/development", [".git", ".svn"], ["*.py", "*.bat", "*.java"], "fred")
        self._match_adapter = MatchAdapter(self.frame, match_criteria)
        self._match_adapter.start()
        self._gauge.Pulse()
        
    def _stop(self, event):
        print 'stop'
        if (self._match_adapter):
            self._match_adapter.stop()
            self._match_adapter = None
        self._gauge.SetValue(0)
        
    def _on_Count(self, evt):
        print '_on_Count'
        print evt.get_value()
                
    def _on_Match(self, evt):
        print '_on_Match'
        if self._match_adapter:
            match_result = evt.get_value()
            print match_result.__dict__
            match_key = (match_result.dir_path, match_result.filename)
            if match_key in self._match_data:
                # existing file
                self._match_data[match_key].append(match_result)
                print "count: ", len(self._match_data[match_key])
            else:
                # new file
                self._match_data[match_key] = [match_result]
            
                                
#     def _redraw_sample_text(self, event):
#         font_name = self._font_name_c.GetStringSelection()
#         if not font_name:
#             return
#         font_size = self._font_size_c.GetValue()
#         font_weight = wx.FONTWEIGHT_BOLD if self._font_weight_c.GetValue() else wx.FONTWEIGHT_NORMAL
#         font_style = wx.FONTSTYLE_ITALIC if self._font_style_c.GetValue() else wx.FONTSTYLE_NORMAL
#         underline = False
#         font = wx.Font(font_size, wx.DEFAULT, font_style, font_weight, underline, font_name)
#         self._sample_text_c.SetFont(font)
#         self._sample_text_c.SetStyle(0, len(self._sample_text_c.GetValue()), wx.TextAttr(self._colour))
#         #if wx.Platform == "__WXMAC__": self.Refresh()
        
#     def _refresh_fonts(self, event):
#         current_font = self._font_name_c.GetStringSelection()
#         font_enum = wx.FontEnumerator()
#         font_enum.EnumerateFacenames()
#         font_names = [name for name in font_enum.GetFacenames() if not name.startswith('@')]
#         font_names.sort()
#         self._font_name_c.Set(font_names)
#         if (not event):
#             current_font = font_names[0]
#         self._font_name_c.SetStringSelection(current_font)
#         #self._font_name_c.SetFirstItemString(current_font)
            
#     def _colour_picked(self, event):
#         print "Colour picked", event.GetColour()
#         self._colour = event.GetColour()
#         colour_rgb = self._colour.red << 16 | self._colour.green << 8 | self._colour.blue
#         hex_value = "%0.6x" % colour_rgb
#         print "Colour hex_value", hex_value
#         self._colour_value_c.SetValue(hex_value)
#         self._redraw_sample_text(event)

#     def _colour_value_changed(self, event):
#         print "Colour value changed"
#         hex_value = '#' + self._colour_value_c.GetValue()
#         self._colour = wx.Colour(*HTMLColorToRGB(hex_value))
#         self._colour_picker_c.SetColour(self._colour) 
#         self._redraw_sample_text(event)
        
###############################################################################

# def HTMLColorToRGB(colorstring):
#     """ convert #RRGGBB to an (R, G, B) tuple """
#     colorstring = colorstring.strip()
#     if colorstring[0] == '#': colorstring = colorstring[1:]
#     if len(colorstring) != 6:
#         raise ValueError, "input #%s is not in #RRGGBB format" % colorstring
#     r, g, b = colorstring[:2], colorstring[2:4], colorstring[4:]
#     r, g, b = [int(n, 16) for n in (r, g, b)]
#     return (r, g, b)
        
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
