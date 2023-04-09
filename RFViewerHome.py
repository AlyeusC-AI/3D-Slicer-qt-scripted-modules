import logging
import codecs
import qt
import slicer
from slicer.ScriptedLoadableModule import *
from RFViewerHomeLib import *
from RFVisualizationLib import RFVisualizationUI, RFLayoutType
from RFReconstruction import *
from RFReconstruction import RFReconstructionLogic
from RFViewerHomeLib import DataLoader, ModuleWidget, ToolbarWidget, createButton, Icons, \
    translatable, ProgressBar, RFSessionSerialization, ExportDirectorySettings, RFViewerWidget, warningMessageBox, wrapInCollapsibleButton
import ScreenCapture
import pydicom
# from oct2py import Oct2Py
import threading
import os.path
from os import path
from datetime import datetime


class RFViewerHome(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "RF Viewer Home"
        self.parent.categories = ["RFCo"]
        self.parent.dependencies = []
        self.parent.contributors = []
        self.parent.helpText = ""
        self.parent.acknowledgementText = ""


@translatable
class RFViewerHomeWidget(RFViewerWidget):
    """
    Widget responsible for instantiating, displaying the different modules and displaying a toolbar for module access
    """

    def __init__(self, parent=None):
        RFViewerWidget.__init__(self, parent)
        self._dataLoaderWidget = None
        self._sessionSerializer = None
        self._toolbarLayout = None
        self._moduleWidget = None
        self._toolbarWidget = None
        self._patientInfoWidget = None
        self._previousModule = None
        self._visualizationWidget = None
        self._reconstructionWidget = None
        self._panoramaReconstructionWidget = None
        self._annotationWidget = None
        self._panoramaWidget = None
        self._segmentationWidget = None
        self._implantWidget = None
        self._exportWidget = None
        self._progressBars = {}
        self._currentWidget = None
        self._moduleWidget1 = None
        self.tmpstr = None
        self.tmpflag_showhidebtn = 1
    def getDataLoader(self):
        return self._dataLoaderWidget

    @classmethod
    def _initDefaultSettings(cls):
        # Set GPU raycasting as default rendering mode
        qt.QSettings().setValue("VolumeRendering/RenderingMethod",
                     "vtkMRMLGPURayCastVolumeRenderingDisplayNode")

        # Disable exit dialog
        qt.QSettings().setValue("MainWindow/DisableExitDialog", True)

        # Enable internationalization
        qt.QSettings().setValue("Internationalization/Enabled", True)

        # Set default values if they don't exist
        cls._setDefaultIfDoesntExist("IndustryType", "Medical")
        cls._setDefaultIfDoesntExist("Internationalization/Language", "ja_JP")

        if qt.QSettings().value("VolumeRendering/GPUMemorySize", "") == "":
            slicer.util.findChild(slicer.app.settingsDialog(
            ), "GPUMemoryComboBox").setCurrentText("6 GB")

    @classmethod
    def _setDefaultIfDoesntExist(cls, key, value):
        if qt.QSettings().value(key, "") == "":
            qt.QSettings().setValue(key, value)

    @staticmethod
    def _initPythonConsoleColors():
        """"Change python prompt colors to be compatible with dark color scheme"""
        lightColor = qt.QColor("#ffb86c")  # orange

        pythonColorMap = {"PromptColorPicker": lightColor,  #
                          "CommandTextColorPicker": lightColor,  #
                          "WelcomeTextColorPicker": lightColor,  #
                          # dark blue
                          "BackgroundColorPicker": qt.QColor("#19232d"),
                          # green
                          "OutputTextColorPicker": qt.QColor("#50fa7b"),
                          "ErrorTextColorPicker": qt.QColor("#ff5555"),  # red
                          }

        settingsDialog = slicer.app.settingsDialog()
        for pickerName, color in pythonColorMap.items():
            try:
                picker = slicer.util.findChild(settingsDialog, pickerName)
                picker.colorChanged(color)

            except RuntimeError:
                logging.error(
                    "Failed to set python console color {}".format(pickerName))

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Initialize settings
        self._initDefaultSettings()
        self._initPythonConsoleColors()

        # Instantiate module widgets
        self._instantiateModuleWidgets()

        # Instantiate data loader and connect data loading and widget progress reporting
        self._dataLoaderWidget = DataLoader()
        self._connectDataLoading()
        self._connectWidgetProgressReporting()

        # Instantiate session serialization object
        self._sessionSerializer = RFSessionSerialization(
            rfWidgets=self._rfModuleWidgets(), loadWidget=self._dataLoaderWidget)

        # Instantiate Toolbar and module widgets
        self._toolbarWidget = ToolbarWidget()
        self._toolbarTileWidget = ToolbarWidget()

        self._stackedWidget = qt.QStackedWidget()
        self._stackedWidget.addWidget(self._toolbarWidget)
        self._stackedWidget.addWidget(self._toolbarTileWidget)
        self._stackedWidget.setCurrentIndex(0)

        self._patientInfoWidget = qt.QLabel()
        # ---レイアウト変更--- 20221227 koyanagi
        self._showhidebutton = qt.QPushButton()
        self._showhidebutton.setIcon(Icons.rightarrow)
        self._showhidebutton.setIconSize(qt.QSize(10, 10))
        self._showhidebutton.setFixedSize(20, 17)
        self._showhidebutton.setStyleSheet(
            "QPushButton {max-width: 20px; min-width: 2px; padding: 0px; padding-right: 7px; padding-left: 2px; border-width: 1px; margin: 0px; border-radius:5px; spacing: 1;}")

        self._moduleWidget = ModuleWidget()
        self._moduleWidget1 = ModuleWidget()
        # Add toolbar button to the top of the dock to always be visible even on module change
        # When loading RFViewerHome inside of Slicer, toolbar will be displayed under the Slicer logo
        self.toolbarButton = wrapInCollapsibleButton(self._stackedWidget, collapsibleText=self.tr("Toolbar"),
                                                     isCollapsed=False)
        self.ModulePanel = slicer.util.findChild(
            slicer.util.mainWindow(), "ModulePanel")
        self.dock_content = slicer.util.findChild(
            slicer.util.mainWindow(), "dockWidgetContents")
        self._patientInfoWidget.setText("")
        # self._patientInfoWidget.setStyleSheet("QLabel { color : orange; }")

        # ---レイアウト変更--- 20221227 koyanagi
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Plain)
        separator.setLineWidth(0)
        separator.setMidLineWidth(0)
        separator.setStyleSheet("background-color: #f4f4f4;")

        # self.dock_content.layout().insertWidget(1, self._showhidebutton)
        # self.dock_content.layout().insertWidget(2, self._patientInfoWidget)
        # self.dock_content.layout().insertWidget(3, self.toolbarButton)

        self.dock_content.layout().insertWidget(1, self._showhidebutton)
        self.dock_content.layout().insertWidget(2, self._patientInfoWidget)
        self.dock_content.layout().insertWidget(3, separator)
        self.dock_content.layout().insertWidget(4, self.toolbarButton)

        self._showhidebutton.clicked.connect(self.showhidePanel)
        # self._showhidebutton.move(10,10)
        # self._showhidebutton.resize(20.30)
        # Add the module widget to the module layout
        self.layout.addWidget(self._moduleWidget1)
        self.layout.addWidget(self._moduleWidget)

        # Configure toolbar sections
        self._configureTileToolbarSection()
        self._configureToolbarFileSection()
        self._configureToolbarReconstructionSection()
        self._configureToolbarAnnotationSection()

        if qt.QSettings().value("IndustryType") == "Medical":
            self._configureToolbarSegmentationSection()
        else:
            self._configureToolbarPanoramaSection()
        # self._configureToolbarPanoramaSection()
    # self._configureToolbarExportSection()
    #    self._configureUndoSection()

        # Close toolbar section and add stretch
        self._toolbarWidget.closeLastSection()
    #    self.layout.addStretch()

        # Load visualisation module by default
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))

        # Load MRB files if any.
        main_window = slicer.util.mainWindow()
        if hasattr(main_window, "commandLineParsed"):
            main_window.commandLineParsed.connect(self._loadCommandLineFiles)
        main_window.onDropEvent.connect(self.onDropEvent)
        # self.dock_content.setFixedWidth(600)

    def onDropEvent(self, event):
        """On drop event, try to load Data as Volume"""
        urls = event.mimeData().urls()
        if len(urls) == 1:
            self.onLoadData(urls[0].toLocalFile())
            tmpfilepath = urls[0].toLocalFile()
            print("tmpfilepath")
            if tmpfilepath.endswith(".mrb"):
                self._sessionSerializer.loadSession(tmpfilepath)
                ExportDirectorySettings.save(tmpfilepath)
            event.acceptProposedAction()

    def makeInt(self, s):
        if type(s) == "string":
            s = s.strip()

        return int(s) if s else 0

    def showhidePanel(self):
        if self.tmpflag_showhidebtn == 1:
               # ---レイアウト変更--- 20221227 koyanagi
            self.dock_content.setMaximumWidth(40)
            self._moduleWidget1.hide()
            self._moduleWidget.hide()
            self._patientInfoWidget.hide()
            self.toolbarButton.hide()
            self.tmpflag_showhidebtn = 0
            self._showhidebutton.setText("")
            self._showhidebutton.setIcon(Icons.leftarrow)
            self._showhidebutton.setIconSize(qt.QSize(10, 10))
        else:
               # ---レイアウト変更--- 20221227 koyanagi
            self.tmpflag_showhidebtn = 1
            self.dock_content.setMaximumWidth(800)
            self._moduleWidget1.show()
            self._moduleWidget.show()
            self._patientInfoWidget.show()
            self.toolbarButton.show()
            self._showhidebutton.setText("")
            self._showhidebutton.setIcon(Icons.rightarrow)
            self._showhidebutton.setIconSize(qt.QSize(10, 10))

    def Average(self, lst):
        return sum(lst) / len(lst)

    def _loadCommandLineFiles(self):
        """
        Load first MRB file in passed command line files if any.
        """
        # getCommandLineFiles method is not available in Slicer
        main_window = slicer.util.mainWindow()
        if not hasattr(main_window, "getCommandLineFiles"):
            return

        files = main_window.getCommandLineFiles()
        for file in files:
            print(file)
            if file.endswith(".mrb"):
                self._sessionSerializer.loadSession(file)
            if file.endswith(".mrb") or file.endswith(".mhd"):
                self.onLoadData(file)
                return

        # RF20220512_yori コマンドから画像開く際は、上でreturnされずここを通る.
        #                その際、iniから現在開いている画像のパスを取得して患者情報読み込む.
        file2 = qt.QSettings().value("ExportDirectory") + "/RFViewerSession.mrb"
        if file2:
            self.onLoadData(file2)
        # RF20220512_end

    def _instantiateModuleWidgets(self):
        self._visualizationWidget = slicer.util.getModuleGui(
            slicer.modules.rfvisualization)
        self._reconstructionWidget = slicer.util.getModuleGui(
            slicer.modules.rfreconstruction)
        self._panoramaReconstructionWidget = slicer.util.getModuleGui(
            slicer.modules.rfpanoramareconstruction)
        self._annotationWidget = slicer.util.getModuleGui(
            slicer.modules.rfannotation)
        self._implantWidget = slicer.util.getModuleGui(
            slicer.modules.rfimplant)
        self._panoramaWidget = slicer.util.getModuleGui(
            slicer.modules.rfpanorama)
        self._segmentationWidget = slicer.util.getModuleGui(
            slicer.modules.rfsegmentation)
        self._exportWidget = slicer.util.getModuleGui(slicer.modules.rfexport)

    def _rfModuleWidgets(self):
        """
        List of all the RFViewerWidgets of the application.
        The widgets are different from the slicer.modules UI which are instances of qSlicerScriptedLoadableModuleWidget.
        """
        return [self,  #
                slicer.modules.RFVisualizationWidget,  #
                slicer.modules.RFReconstructionWidget,  #
                slicer.modules.RFAnnotationWidget,  #
                slicer.modules.RFImplantWidget,  #
                slicer.modules.RFPanoramaWidget,  #
                slicer.modules.RFPanoramaReconstructionWidget,  #
                slicer.modules.RFSegmentationWidget,  #
                slicer.modules.RFExportWidget]

    def _connectDataLoading(self):
        for moduleWidget in self._rfModuleWidgets():
            self._dataLoaderWidget.volumeNodeChanged.connect(
                moduleWidget.setVolumeNode)

    def _connectWidgetProgressReporting(self):
        for moduleWidget in self._rfModuleWidgets():
            self.connectProgressSignal(moduleWidget)
            moduleWidget.setLoadWidget(self._dataLoaderWidget)

    def setPatientId(self, patientId):
        lm = slicer.app.layoutManager()
        sliceNames = lm.sliceViewNames()
        for sliceName in sliceNames:
            sliceWidget = lm.sliceWidget(sliceName)
            sliceView = sliceWidget.sliceView()
            sliceView.setPatientId(patientId)

    def onLoadData(self, filePath):
        if not filePath:
            return
        filePath = os.path.join(os.path.dirname(filePath), "NAOMICT_UTF8.mnri")
        IndustryTypeValue = qt.QSettings().value("IndustryType")
        self._patientInfoWidget.setText("")
        try:
            mnri_settings = RFReconstructionLogic.MNRISettings(filePath)

            WindowCenter = self.makeInt(
                mnri_settings.value("Frame/WindowCenter"))
            WindowWidth = self.makeInt(
                mnri_settings.value("Frame/WindowWidth"))
            qt.QSettings().setValue("WindowCenter", WindowCenter)
            qt.QSettings().setValue("WindowWidth", WindowWidth)
            volx = self.makeInt(mnri_settings.value("BackProjection/VolXDim"))
            if volx > 0:
                qt.QSettings().setValue("volx", volx)
            # RF20220512_yori ID7桁対策. 下記関数はRFReconstruction.py内に追加済みのもの.
            patientId = mnri_settings.IDvalue("DicomPatientInfo/PatientId")
            # RF20220512_else
            # patientId = mnri_settings.value("DicomPatientInfo/PatientId")
            # RF20220512_end
            self.setPatientId(patientId)
            # self.ui.raycastSelector.setCurrentIndex(0)

            patientName = mnri_settings.value("DicomPatientInfo/PatientName")
            patientSex = self.makeInt(
                mnri_settings.value("DicomPatientInfo/PatientSex"))
            # RF20220512_yori 日本語で.
            if patientSex == 1:
                patientSexStr = "男性"
            elif patientSex == -1:
                patientSexStr = "女性"
            else:
                patientSexStr = ""
            # RF20220512_else
            # if patientSex == 1:
            #    patientSexStr = "Male"
            # elif patientSex == -1:
            #    patientSexStr = "Female"
            # else:
            #    patientSexStr = "Unknown"
            # RF20220512_end
            y = self.makeInt(mnri_settings.value(
                "DicomPatientInfo/PatientBirthYear"))
            m = self.makeInt(mnri_settings.value(
                "DicomPatientInfo/PatientBirthMonth"))
            d = self.makeInt(mnri_settings.value(
                "DicomPatientInfo/PatientBirthDate"))
            if y > 0 and m > 0 and d > 0:
                BithdayDate = qt.QDate(y, m, d).toString("yyyy.MM.dd")
            else:
                BithdayDate = "2000.1.1"
            datetime = qt.QDate.currentDate()
            strnow = datetime.toString(qt.Qt.ISODate)
            strnow = strnow.replace("-", ".")
            # RF20220512_yori 項目名追記＋今日の日付は無しで.
            tmpstr = ""
            if IndustryTypeValue == "Industrial":
                tmpstr = "ID: " + str(patientId) + " / 品名: " + patientName
            else:
                # ---レイアウト変更--- 20221227 koyanagi
                tmpstr = "ID:" + str(patientId) + " /名前:" + patientName + \
                                     " /性別:" + patientSexStr + " /生年月日:" + BithdayDate
                # tmpstr = "患者ID: " + str(patientId) + " / 患者名: " + patientName + " / 性別: " + patientSexStr + " / 生年月日: " +BithdayDate
            self._patientInfoWidget.setText(tmpstr)
            # RF20220512_else
            # tmpstr = str(patientId) + " /" + patientName + " /" + patientSexStr + " /" +BithdayDate + " /" +strnow
            # if IndustryTypeValue == "Industrial":
            #    self._patientInfoWidget.setText(str(patientId) + " /" + strnow)
            # else:
            #    self._patientInfoWidget.setText(tmpstr)
            # RF20220512_end
        except:
            self._patientInfoWidget.setText("")
            qt.QSettings().setValue("WindowCenter", 3400)
            qt.QSettings().setValue("WindowWidth", 750)

    def captureTileView(self):
        print("capture!")

    def _configureTileToolbarSection(self):
        self._toolbarTileWidget.createSection(self.tr("TileView"))

        backToMainButton = createButton(
            "", self.changeToMainLayout)
        backToMainButton.setIcon(Icons.leftarrow)
        self._toolbarTileWidget.addButton(backToMainButton)

        tileCaptureButton = createButton(
            "", self.captureTileView)
        tileCaptureButton.setIcon(Icons.rightarrow)
        self._toolbarTileWidget.addButton(tileCaptureButton)

        self._toolbarTileWidget.createSection()

    def _configureToolbarFileSection(self):
        self._toolbarWidget.createSection(self.tr("File"))
       # Save session
        reconstruction3dButton = createButton(
            "", self.loadReconstructionModule)
        reconstruction3dButton.setIcon(Icons.reconstruction3d)
        self._toolbarWidget.addButton(reconstruction3dButton)

        sessionSaveButton = createButton(
            "", lambda *x: self._sessionSerializer.onSaveSession())
        sessionSaveButton.setIcon(Icons.sessionSave)
        self._toolbarWidget.addButton(sessionSaveButton)

        exportDICOMButton = createButton("", self.loadExportModule)
        exportDICOMButton.setIcon(Icons.exportDICOM)
        self._toolbarWidget.addButton(exportDICOMButton)

        tileViewButton = createButton("", self.changeToTileLayout)
        tileViewButton.setIcon(Icons.leftarrow)
        self._toolbarWidget.addButton(tileViewButton)

    def _configureToolbarReconstructionSection(self):
        self._toolbarWidget.createSection()

        takeScreenshotButton = createButton("", self.loadTakeScreenshotModule)
        takeScreenshotButton.setIcon(Icons.takeScreenshot)
        self._toolbarWidget.addButton(takeScreenshotButton)

        DVDExportButton = createButton("", self.DVDexportModule)
        DVDExportButton.setIcon(Icons.DVDexport)
        self._toolbarWidget.addButton(DVDExportButton)

        resetMPRButton = createButton("", self.loadResetMPRModule)
        resetMPRButton.setIcon(Icons.ResetMPR)
        self._toolbarWidget.addButton(resetMPRButton)

        AllResetButton = createButton("", self.AllResetModule)
        AllResetButton.setIcon(Icons.AllReset)
        self._toolbarWidget.addButton(AllResetButton)

        # for Debug.
        DebuggerAttachButton = createButton("", self.DebuggerAttach)
        DebuggerAttachButton.setIcon(Icons.rightarrow)
        self._toolbarWidget.addButton(DebuggerAttachButton)

    def _configureToolbarAnnotationSection(self):
        self._toolbarWidget.createSection(self.tr("Measuring Instruments"))
        # self._toolbarWidget.addButton(createButton(self.tr("Measuring Instruments"), self.loadAnnotationModule))
        # self._toolbarWidget.addButton(
        #     createButton("", lambda *x: self.loadAnnotationModule, icon=Icons.measureTool), toolTip=self.tr("Measuring Instruments"))

        measureToolButton = createButton("", self.loadAnnotationModule)
        measureToolButton.setIcon(Icons.measureTool)
        self._toolbarWidget.addButton(measureToolButton)

        AnnotationAngleButton = createButton(
            "", self.loadAnnotationAngleModule)
        AnnotationAngleButton.setIcon(Icons.AnnotationAngle)
        self._toolbarWidget.addButton(AnnotationAngleButton)

    def _configureToolbarPanoramaSection(self):
        self._toolbarWidget.createSection(self.tr("描画ツール"))

        implantToolButton = createButton("", self.loadImplantModule)
        implantToolButton.setIcon(Icons.implantTool)
        self._toolbarWidget.addButton(implantToolButton)

        # panoramaToolButton = createButton("", self.loadPanoramaModule)
        # panoramaToolButton.setIcon(Icons.PanoramaDisplay)
        # self._toolbarWidget.addButton(panoramaToolButton)

        AnnotationLineButton = createButton("", self.loadAnnotationLineModule)
        AnnotationLineButton.setIcon(Icons.AnnotationLine)
        self._toolbarWidget.addButton(AnnotationLineButton)

    def _configureToolbarSegmentationSection(self):
        SegmentationButton = createButton("", self.loadSegmentationModule)
        SegmentationButton.setIcon(Icons.Segmentation)
        # self._toolbarWidget.addButton(SegmentationButton)

    def _configureToolbarExportSection(self):
        self._toolbarWidget.createSection()
        self._toolbarWidget.addButton(createButton(
            self.tr("Export Tools"), self.loadExportModule))

    def _configureUndoSection(self):
        self._toolbarWidget.createSection()
        self._toolbarWidget.addButton(createButton(self.tr("Undo"), self.undo))

    def loadAnnotationLineModule(self):
        self._currentWidget = slicer.modules.RFAnnotationWidget
        self._moduleWidget.setModule(
            self._annotationWidget, self.tr("Annotations"))
        self._currentWidget.onModuleOpened()
        self._currentWidget.canalWidget.addCanalButton.click()

    def loadAnnotationAngleModule(self):
        self._currentWidget = slicer.modules.RFAnnotationWidget
        self._moduleWidget.setModule(
            self._annotationWidget, self.tr("Annotations"))
        self._currentWidget.onModuleOpened()
        self._currentWidget._widget.createAnglePushButton.click()

    def connectProgressSignal(self, widget):
        widget.addProgressBar.connect(self.onAddProgressBar)
        widget.removeProgressBar.connect(self.onRemoveProgressBar)

    def onAddProgressBar(self, progressName):
        if progressName in self._progressBars:
            return

        progressBar = ProgressBar(progressName)
        self._progressBars[progressName] = progressBar
        self.layout.addWidget(progressBar)

    def loadSegmentationModule(self):
        self._currentWidget = slicer.modules.RFSegmentationWidget
        self._moduleWidget.setModule(
            self._segmentationWidget, self.tr("Segmentation"))
        self._currentWidget.onModuleOpened()
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))

    def onRemoveProgressBar(self, progressName):
        if progressName not in self._progressBars:
            return

        progressBar = self._progressBars[progressName]
        self.layout.removeWidget(progressBar)
        progressBar.setVisible(False)
        del self._progressBars[progressName]

    def loadTakeScreenshotModule(self):
        self._currentWidget = slicer.modules.RFExportWidget
        self._currentWidget.onModuleOpened()
        self._currentWidget.takeScreenshotButton.click()

    def DVDexportModule(self):
        self._currentWidget = slicer.modules.RFExportWidget
        self._currentWidget.onModuleOpened()
        self._currentWidget.DVDexportButton.click()

    def AllResetModule(self):

        msg = qt.QMessageBox()
        msg.setIcon(qt.QMessageBox.Information)

        msg.setText("全ての画像編集をリセットします。")
        msg.setInformativeText("よろしいですか？")

        pButtonYes = msg.addButton("はい", qt.QMessageBox.YesRole)
        msg.addButton("キャンセル", qt.QMessageBox.NoRole)
        # cancelBtn.connect(self.msgbtn)
        msg.exec_()

        if msg.clickedButton() == pButtonYes:
            if path.exists(self._sessionSerializer._lastSessionPath()):

                self._sessionSerializer.loadSession(
                    self._sessionSerializer._lastSessionPath())
                views = slicer.util.getNodesByClass(
                    'vtkMRMLSliceCompositeNode')
                for view in views:
                    view.SetSliceIntersectionVisibility(False)
                # Set 3D view
                sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
                for slice in sliceNodes:
                    slice.SetWidgetVisible(False)
                self._currentWidget1 = slicer.modules.RFVisualizationWidget
                self._currentWidget1.ui.setMIPThickness5Button()

    def DebuggerAttach(self):
        msg = qt.QMessageBox()
        msg.setIcon(qt.QMessageBox.Information)

        msg.setText("DebuggerのAttachをwaitします。")
        msg.setInformativeText("よろしいですか？")

        pButtonYes = msg.addButton("はい", qt.QMessageBox.YesRole)
        msg.addButton("キャンセル", qt.QMessageBox.NoRole)
        msg.exec_()

        if msg.clickedButton() == pButtonYes:
            import ptvsd
            ptvsd.enable_attach()
            ptvsd.wait_for_attach()

            msgAttached = qt.QMessageBox()
            msgAttached.setIcon(qt.QMessageBox.Information)
            msgAttached.setText("Debugger Attached!!")
            msg.addButton("OK", qt.QMessageBox.NoRole)
            msgAttached.exec_()
    def tabIndexChanged(self, index):
        layoutManager = slicer.app.layoutManager()
        tabBar_index = slicer.util.mainWindow().CentralWidget.CentralWidgetLayoutFrame.findChild("QTabBar").currentIndex
        print (tabBar_index)
        if tabBar_index == 0:
            self._prevLayout = layoutManager.layout
        else:
            self._stackedWidget.setCurrentIndex(0)
            layoutManager.setLayout(self._prevLayout)
            slicer.modules.rfvisualization.widgetRepresentation().self().ui.setCurrentIndex(0)

    def changeToMainLayout(self):
        layoutManager = slicer.app.layoutManager()
        self._stackedWidget.setCurrentIndex(0)
        layoutManager.setLayout(self._prevLayout)

    def changeToTileLayout(self):
        layoutManager = slicer.app.layoutManager()
        self._prevLayout = layoutManager.layout
        self._stackedWidget.setCurrentIndex(1)
        layoutManager.setLayout(RFLayoutType.RFTileLayout)
        tabBar = slicer.util.mainWindow().CentralWidget.CentralWidgetLayoutFrame.findChild("QTabBar")
        tabBar.currentChanged.connect(self.tabIndexChanged)

        slicer.modules.rfvisualization.widgetRepresentation().self().ui.setCurrentIndex(1)

    def loadVisualisationModule(self):
        self._currentWidget = slicer.modules.RFVisualizationWidget
        self._moduleWidget.setModule(
            self._visualizationWidget, self.tr("Visualization"))
        self._currentWidget.onModuleOpened()

    def loadReconstructionModule(self):
        self._currentWidget = slicer.modules.RFReconstructionWidget
        self._moduleWidget.setModule(
            self._reconstructionWidget, self.tr("Reconstruction"))
        slicer.modules.RFReconstructionWidget.setLoadWidget(
            self._dataLoaderWidget)
        self._currentWidget.onModuleOpened()
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))

    def loadPanoramaReconstructionModule(self):
        self._moduleWidget.setModule(
            self._panoramaReconstructionWidget, self.tr("Panorama Reconstruction"))
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))

    def loadAnnotationModule(self):
        self._currentWidget = slicer.modules.RFAnnotationWidget
        self._moduleWidget.setModule(
            self._annotationWidget, self.tr("Annotations"))
        self._currentWidget.onModuleOpened()
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))
        self._currentWidget._widget.createLinePushButton.click()

    def loadImplantModule(self):
        self._currentWidget = slicer.modules.RFImplantWidget
        self._moduleWidget.setModule(self._implantWidget, self.tr("Implants"))
        self._currentWidget.onModuleOpened()
        self._moduleWidget1.setModule(self._visualizationWidget, self.tr("Visualization"))

    def loadPanoramaModule(self):
        self._currentWidget = slicer.modules.RFPanoramaWidget
        self._moduleWidget.setModule(self._panoramaWidget, self.tr("Panorama"))
        self._currentWidget.onModuleOpened()
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))

    def loadSegmentationModule(self):
        self._currentWidget = slicer.modules.RFSegmentationWidget
        self._moduleWidget.setModule(
            self._segmentationWidget, self.tr("Segmentation"))
        self._currentWidget.onModuleOpened()
        self._moduleWidget1.setModule(
            self._visualizationWidget, self.tr("Visualization"))

    def loadExportModule(self):
        self._currentWidget = slicer.modules.RFExportWidget
        self._currentWidget.onModuleOpened()
        self._currentWidget.exportDicomButton.click()

    def loadResetMPRModule(self):
        # self._currentWidget = slicer.modules.RFExportWidget
        # self._currentWidget.onModuleOpened()
        # self._currentWidget.exportDicomButton.click()
        layoutManager = slicer.app.layoutManager()
        for sliceViewName in layoutManager.sliceViewNames():
            sliceWidget = layoutManager.sliceWidget(sliceViewName)
            sliceControlWidget = sliceWidget.sliceController()
            sliceControlWidget.resetSliceToBackground()
            sliceControlWidget.rotateSliceToBackground()
            sliceControlWidget.fitSliceToBackground()

    def undo(self):
        if self._currentWidget:
            self._currentWidget.undo()

    def onSessionAboutToBeSaved(self):
        parameterNode = self.getParameterNode()
        parameterNode.SetParameter(
            "CurrentNodeID", self._dataLoaderWidget.getCurrentNodeID())

    def onSessionLoaded(self):
        parameterNode = self.getParameterNode()
        self._dataLoaderWidget.restoreCurrentNodeFromID(
            parameterNode.GetParameter("CurrentNodeID"))

    def reconstructAndSaveSession(self, mnriPath, mrbOutputPath):
        # Disable loading notifications
        self._dataLoaderWidget.setVolumeAddedNotificationEnabled(False)
        # Reconstruct synchronously
        mnri_settings = RFReconstructionLogic.MNRISettings(mnriPath)
        try:
            typeValue = int(mnri_settings.value("Frame/Type"))
            if typeValue != 1:
                cli_node = slicer.modules.RFReconstructionWidget.reconstruct(
                    mnriPath=mnriPath, isCliSynchronous=True)
            else:
                cli_node = slicer.modules.RFReconstructionWidget.reconstructForTwoImages(
                    mnriPath)
        except:
            cli_node = slicer.modules.RFReconstructionWidget.reconstruct(
                mnriPath=mnriPath, isCliSynchronous=True)

        # # Reconstruct synchronously
        # cli_node = slicer.modules.RFReconstructionWidget.reconstruct(mnriPath=mnriPath, isCliSynchronous=True)

        # Save session if reconstruction was successful
        if not cli_node.GetStatusString() == 'Completed':
            warningMessageBox(self.tr("Reconstruction Failed"),
                              f"{cli_node.GetErrorText()}")
            self._dataLoaderWidget.setVolumeAddedNotificationEnabled(True)
            return

        # Set new volume for the different widgets
        for widget in self._rfModuleWidgets():
            widget.setVolumeNode(self._dataLoaderWidget.getCurrentVolumeNode())

        # Wait until all widgets are updated with reconstructed volume and save the session
        slicer.app.processEvents()

        # Save session
        self._sessionSerializer.saveSession(
            mrbOutputPath, showMessageBox=False)

        # Enable notifications
        self._dataLoaderWidget.setVolumeAddedNotificationEnabled(True)


class RFViewerHomeLogic(ScriptedLoadableModuleLogic):
    """Empty logic class for the module to avoid error report on module loading"""
    pass
