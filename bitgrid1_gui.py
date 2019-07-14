# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version Oct 26 2018)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc

###########################################################################
## Class MyFrame1
###########################################################################

class MyFrame1 ( wx.Frame ):

    def __init__( self, parent ):
        wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Mike's Bitgrid Simulator", pos = wx.DefaultPosition, size = wx.Size( 628,393 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

        self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

        self.m_menubar2 = wx.MenuBar( 0 )
        self.m_menu2 = wx.Menu()
        self.m_menuItem1 = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"&New", wx.EmptyString, wx.ITEM_NORMAL )
        self.m_menu2.Append( self.m_menuItem1 )

        self.m_menuItem5 = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"&Open", wx.EmptyString, wx.ITEM_NORMAL )
        self.m_menu2.Append( self.m_menuItem5 )

        self.m_menuItem6 = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"&Save", wx.EmptyString, wx.ITEM_NORMAL )
        self.m_menu2.Append( self.m_menuItem6 )

        self.m_menuItem7 = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Save &as", wx.EmptyString, wx.ITEM_NORMAL )
        self.m_menu2.Append( self.m_menuItem7 )

        self.m_menu2.AppendSeparator()

        self.m_menuItem8 = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"E&xit", wx.EmptyString, wx.ITEM_NORMAL )
        self.m_menu2.Append( self.m_menuItem8 )

        self.m_menubar2.Append( self.m_menu2, u"&File" )

        self.m_menu3 = wx.Menu()
        self.m_menuItem9 = wx.MenuItem( self.m_menu3, wx.ID_ANY, u"About"+ u"\t" + u"F1", wx.EmptyString, wx.ITEM_NORMAL )
        self.m_menu3.Append( self.m_menuItem9 )

        self.m_menubar2.Append( self.m_menu3, u"&Help" )

        self.SetMenuBar( self.m_menubar2 )


        self.Centre( wx.BOTH )

        # Connect Events
        self.Bind( wx.EVT_MENU, self.ByeBye, id = self.m_menuItem8.GetId() )
        self.Bind( wx.EVT_MENU, self.ShowHelp, id = self.m_menuItem9.GetId() )

    def __del__( self ):
        pass


    # Virtual event handlers, overide them in your derived class
    def ByeBye( self, event ):
        event.Skip()

    def ShowHelp( self, event ):
        event.Skip()


###########################################################################
## Class AboutBox
###########################################################################

class AboutBox ( wx.Dialog ):

    def __init__( self, parent ):
        wx.Dialog.__init__ ( self, parent, id = wx.ID_ANY, title = u"About Bitgrid", pos = wx.DefaultPosition, size = wx.Size( 517,405 ), style = wx.CLOSE_BOX|wx.DEFAULT_DIALOG_STYLE )

        self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

        bSizer1 = wx.BoxSizer( wx.VERTICAL )

        self.m_staticText1 = wx.StaticText( self, wx.ID_ANY, u"This project is my first GUI representation of an idea I've had in my head for decades.", wx.DefaultPosition, wx.DefaultSize, wx.ALIGN_CENTER_HORIZONTAL )
        self.m_staticText1.Wrap( -1 )

        bSizer1.Add( self.m_staticText1, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL, 5 )


        bSizer1.Add( ( 0, 0), 1, wx.EXPAND, 5 )

        self.m_button1 = wx.Button( self, wx.ID_ANY, u"OK", wx.DefaultPosition, wx.DefaultSize, 0 )
        bSizer1.Add( self.m_button1, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL, 5 )


        self.SetSizer( bSizer1 )
        self.Layout()

        self.Centre( wx.BOTH )

        # Connect Events
        self.m_button1.Bind( wx.EVT_BUTTON, self.CloseAbout )

    def __del__( self ):
        pass


    # Virtual event handlers, overide them in your derived class
    def CloseAbout( self, event ):
        event.Skip()


