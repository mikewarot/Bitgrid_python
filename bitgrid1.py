import wx
import bitgrid1_gui


#inherit from the MainFrame created in wxFowmBuilder and create CalcFrame
class OurFrame(bitgrid1_gui.MyFrame1):
    #constructor
    def __init__(self,parent):
        #initialize parent class
        bitgrid1_gui.MyFrame1.__init__(self,parent)
 
    #what to when 'Exit' is clicked
    #wx calls this function with and 'event' object
    def ByeBye(self,event):
        print("Closing down now")
        self.Close()

    #when the Help button is clicked
    def ShowHelp(self,event):
        print("Showing About Box")
        helpdialog = OurHelp(None)
        helpdialog.ShowModal()

class OurHelp(bitgrid1_gui.AboutBox):
    #constructor
    def __init__(self,parent):
        #initialize parent class
        bitgrid1_gui.AboutBox.__init__(self, parent)

    def CloseAbout(self, event):
        print("Closing about box")
        self.Destroy()
        



app = wx.App()
frame = OurFrame(None)
frame.Show()
app.MainLoop()

