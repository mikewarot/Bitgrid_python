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

    #update the inputs
    def UpdateInputs(self, event):
        print("updating inputs")
        programcode = self.cellHex.GetLineText(0)
        inputvalue = 0
        if self.inUp.GetValue():    inputvalue = inputvalue + 8
        if self.inLeft.GetValue():  inputvalue = inputvalue + 4
        if self.inRight.GetValue(): inputvalue = inputvalue + 2
        if self.inDown.GetValue():  inputvalue = inputvalue + 1
        print("Input value %0.1x"%inputvalue)
        print("Program %s"%programcode)
        

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

