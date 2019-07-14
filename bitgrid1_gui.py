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

        gbSizer1 = wx.GridBagSizer( 0, 0 )
        gbSizer1.SetFlexibleDirection( wx.BOTH )
        gbSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

        self.inLeft = wx.ToggleButton( self, wx.ID_ANY, u"Left Input", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.inLeft, wx.GBPosition( 2, 0 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.inUp = wx.ToggleButton( self, wx.ID_ANY, u"Up Input", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.inUp.SetFont( wx.Font( wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

        gbSizer1.Add( self.inUp, wx.GBPosition( 1, 1 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.inRight = wx.ToggleButton( self, wx.ID_ANY, u"Right Input", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.inRight, wx.GBPosition( 2, 2 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.inDown = wx.ToggleButton( self, wx.ID_ANY, u"Down Input", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.inDown, wx.GBPosition( 3, 1 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.m_staticText2 = wx.StaticText( self, wx.ID_ANY, u"Program (Hex)", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.m_staticText2.Wrap( -1 )

        gbSizer1.Add( self.m_staticText2, wx.GBPosition( 5, 0 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.cellHex = wx.TextCtrl( self, wx.ID_ANY, u"0123456789abcdef", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.cellHex, wx.GBPosition( 5, 1 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.outUp = wx.CheckBox( self, wx.ID_ANY, u"Up Output", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.outUp, wx.GBPosition( 8, 1 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.outDown = wx.CheckBox( self, wx.ID_ANY, u"Down Output", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.outDown, wx.GBPosition( 10, 1 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.outLeft = wx.CheckBox( self, wx.ID_ANY, u"Left Output", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.outLeft, wx.GBPosition( 9, 0 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )

        self.outRight = wx.CheckBox( self, wx.ID_ANY, u"Right Output", wx.DefaultPosition, wx.DefaultSize, 0 )
        gbSizer1.Add( self.outRight, wx.GBPosition( 9, 2 ), wx.GBSpan( 1, 1 ), wx.ALL, 5 )


        self.SetSizer( gbSizer1 )
        self.Layout()

        self.Centre( wx.BOTH )

        # Connect Events
        self.Bind( wx.EVT_MENU, self.ByeBye, id = self.m_menuItem8.GetId() )
        self.Bind( wx.EVT_MENU, self.ShowHelp, id = self.m_menuItem9.GetId() )
        self.inLeft.Bind( wx.EVT_TOGGLEBUTTON, self.UpdateInputs )
        self.inUp.Bind( wx.EVT_TOGGLEBUTTON, self.UpdateInputs )
        self.inRight.Bind( wx.EVT_TOGGLEBUTTON, self.UpdateInputs )
        self.inDown.Bind( wx.EVT_TOGGLEBUTTON, self.UpdateInputs )
        self.outUp.Bind( wx.EVT_CHECKBOX, self.outChanged )
        self.outDown.Bind( wx.EVT_CHECKBOX, self.outChanged )
        self.outLeft.Bind( wx.EVT_CHECKBOX, self.outChanged )
        self.outRight.Bind( wx.EVT_CHECKBOX, self.outChanged )

    def __del__( self ):
        pass


    # Virtual event handlers, overide them in your derived class
    def ByeBye( self, event ):
        event.Skip()

    def ShowHelp( self, event ):
        event.Skip()

    def UpdateInputs( self, event ):
        event.Skip()




    def outChanged( self, event ):
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


