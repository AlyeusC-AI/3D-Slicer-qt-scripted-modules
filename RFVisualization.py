import qt
import slicer
from slicer.ScriptedLoadableModule import *
import vtk
from RFReconstruction import RFReconstructionLogic
import RFViewerHomeLib
from RFViewerHomeLib import wrapInQTimer, translatable, RFViewerWidget, showVolumeOnSlices,showVolumeOnSlice, warningMessageBox, \
  getViewBySingletonTag,ExportDirectorySettings 
from RFVisualizationLib import RFLayoutType, layoutSetup, layoutBackgroundSetup, RFVisualizationUI, IndustryType, \
  closestPowerOfTen, getAll3DViewNodes, createDiscretizableColorTransferFunctionFromColorPreset, \
  createColorNodeFromVolumePropertyNode, ViewTag
import threading

from datetime import datetime
import numpy as np
import pydicom
import os
# from pydicom.pixel_data_handlers.util import apply_voi_lut
# from numba import jit, cuda ,njit,float64, int32
# import numba  
# import pylops

class RFVisualization(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "RF Visualization" # TODO make this more human readable by adding spaces
    self.parent.categories = ["RFCo"]
    self.parent.dependencies = []
    self.parent.contributors = [] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = ""
    self.parent.acknowledgementText = ""


@translatable
class RFVisualizationWidget(RFViewerWidget):
  def __init__(self, parent):
    RFViewerWidget.__init__(self, parent)
    self.volumeNode = None

    self._layoutManager = None
    self._vrLogic = None

    self._currentPreset3D = None
    self._currentPreset2D = None
    self._synchronizeViews = False
    self._currentVRMode = slicer.vtkMRMLViewNode().Composite
    self._currentColor = None # Means that the color is the current preset3D color
    self._map3DColorToColorTableNode = {}

    self._previousThresholdPreset = 0.0
    self._isLoadingState = False

    self._displayNodeVisibility = {}
    self._roisVisibility = {}
    self._viewVisibility = {}
    #--- for cephalometric 20220924 koyanagi --- add
    self._OrientationMarkerVisibility = True
    self._RulerVisibility = True
    #-------------------------------------------
    #--- for cephalometric & Speed up 20220924 koyanagi --- add
    self._FractionSetting = True
    #-------------------------------------------
    #---- セファロ用設定の復元 20230124 koyanagi -------------
    self._SlabMode_Setting = {}
    self._MipThickness_Setting = {}
    self._NumberOfSlices_Setting = {}
    #-------------------------------------------

    self._updatingSliceNodes = False
    self._updatingSephaloCorrectionValue = False
    sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
    for sliceNode in sliceNodes:
      sliceNode.zoomChangeObserverTag = sliceNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.sliceModified)

  def getVolumeDisplayNode3D(self):
    return self._vrLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode)
  def setVolumeNode(self, volumeNode):
    self.volumeNode = volumeNode
    # Fix initial raycast state on volume loading
    # self.ui.raycastSelector.setCurrentIndex(0)

    if self.volumeNode and not self.getVolumeDisplayNode3D():
      self._vrLogic.CreateDefaultVolumeRenderingNodes(self.volumeNode)
    
    # print(volumeNode)
    self.ui.setVolumeNode(volumeNode=volumeNode, displayNode3D=self.getVolumeDisplayNode3D(),
                          isLoadingState=self._isLoadingState)

    # If volume node was cleared, presets should not be set
    if not self.volumeNode:
      return

    self.setPreset3D(self._currentPreset3D)
    self.setPreset2D(self._currentPreset2D)
    self.setVRMode(self._currentVRMode)
    self.setColorTo3D(self._currentColor)

    if self._isLoadingState:
      return

    self.fit3DViewsToVolume()
    if self.industry == IndustryType.Dental:
      self.rotateAxialViewInDentalConvention()
    self.counts = 0
    showVolumeOnSlices(self.volumeNode.GetID(), ViewTag.mainViewTags())
  
  @staticmethod
  def rotateAxialViewInDentalConvention():
    axialView = getViewBySingletonTag(ViewTag.Axial)
    axialDentalRotationMatrix = [[-1, 0, 0], [0, -1, 0], [0, 0, -1]]
    axialRASMatrix = axialView.GetSliceToRAS()

    for i, row in enumerate(axialDentalRotationMatrix):
      for j, val in enumerate(row):
        axialRASMatrix.SetElement(i, j, val)

    axialView.UpdateMatrices()

  @wrapInQTimer
  def fit3DViewsToVolume(self):
    # Fit 3D views to new volume
    slicer.util.resetThreeDViews()

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    #
    # Initialize attributes
    #
    try:
      self.industry = IndustryType[qt.QSettings().value("IndustryType")]
    except KeyError:
      self.industry = IndustryType.Medical
    self._layoutManager = slicer.app.layoutManager()
    self._vrLogic = slicer.modules.volumerendering.logic()

    # Apply default 3D Preset
    self._currentPreset3D = self._defaultIndustry3DPreset()
    self.setPreset3D(self._currentPreset3D)

    #
    # Setup Layouts
    #
    layoutSetup(self._layoutManager)
    layoutBackgroundSetup(self._layoutManager.threeDWidget(0).mrmlViewNode())
    self.ui = RFVisualizationUI(self._vrLogic, self._currentPreset3D, self.industry)
    self.layout.addWidget(self.ui)
    self.setSlicerLayout(RFLayoutType.RFDefaultLayout)

    # Apply default 2D preset
    self._currentPreset2D = self._defaultIndustry2DPreset()
    self.setPreset2D(self._currentPreset2D)

    #
    # Connections
    #
    self.ui.layoutSelector.connect("currentIndexChanged(int)", self.onLayoutSelect)
    self.ui.preset3DSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onPreset3DSelect)
    self.ui.preset2DSelector.connect("currentIndexChanged(int)", self.onPreset2DSelect)
    self.ui.vrModeSelector.connect("currentIndexChanged(int)", self.onVRModeSelect)
    self.ui.colorSelector.connect("currentIndexChanged(int)", self.onColorSelect)
    self.ui.shiftSlider.connect("valueChanged(double)", self.onShiftSliderChanged)
    self.ui.synchronizeCheckbox.connect("stateChanged(int)", self.onSynchronizeChanged)
    self.ui.displayResliceCursorCheckbox.connect("stateChanged(int)", self.onResliceCursorDisplayed)
    self.ui.slabThicknessSlider.connect("valueChanged(int)", self.onSlabThicknessSliderChanged)
    self.ui.thicknessSelector.connect("currentIndexChanged(int)", self.onMIPThicknessChanged)
    self.ui.displayROICheckBox.connect("stateChanged(int)", self.onROIDisplayed)
    self.ui.raycastSelector.connect("currentIndexChanged(int)", self.onRaycastChanged)
    #--- for cephalometric 20220924 koyanagi --- add
    self.ui.FOVSelector.connect("currentIndexChanged(int)", self.onFOVChanged)#セファロ拡大率補正用コンボボックス
    self.ui.OrientationMarkerCheckBox.connect("stateChanged(int)", self.onOrientationMarkerChanged)#マーカーキューブの表示・非表示
    self.onOrientationMarkerChanged()#初期設定値の内容を反映させるため #---ルーラー非表示対応--- 20230105 Yao-sama
    self.ui.rulerCheckBox.connect("stateChanged(int)", self.onRulerChanged)#ルーラーの表示・非表示
    self.onRulerChanged()#初期設定値の内容を反映させるため #---ルーラー非表示対応--- 20230105 Yao-sama
    #-------------------------------------------
    #--- for cephalometric & Speed up 20220924 koyanagi --- add
    self.ui.fractionCheckBox.connect("stateChanged(int)", self.onFractionChanged)#ルーラーの表示・非表示
    #-------------------------------------------

    self.ui.numCombo.connect("currentIndexChanged(int)", self.onTileLayoutChanged)
    self.ui.directionCombo.connect("currentIndexChanged(int)", self.onTileOrientationChanged)
    self.ui.sliceIntervalSlider.connect("valueChanged(int)", self.onTileIntervalSliderChanged)
    self.ui.sliceIntervalSelector.connect("currentIndexChanged(int)", self.onTileIntervalSelectorChanged)
    self.ui.slicePositionSlider.connect("valueChanged(int)", self.onTilePositionSliderChanged)
    self.ui.slicePositionSelector.connect("currentIndexChanged(int)", self.onTilePositionSelectorChanged)


    #タブビュー機能追加　初期表示変更　タブレイアウト＆SlicerLayoutFourUpView
    layoutManager = slicer.app.layoutManager()
    mainLayout = layoutManager.layoutLogic().GetLayoutNode().GetLayoutDescription(RFLayoutType.RFDefaultLayout)
    
    slicer.modules.RFViewerHomeWidget.centralWidgetLayout(mainLayout,"","",0)
    #-------------------------------------------

    #20220804_Koyanagi
    # 前回のレイアウト設定の引継ぎ  2022/8/4  小柳
    #lastSessionLayout = qt.QSettings().value("MainWindow/layout")
    #self.setSlicerLayout(lastSessionLayout)
    #self.ui.layoutSelector.setCurrentIndex(lastSessionLayout)
    #20220804_Koyanagi_end

    # Add vertical spacer
    self.layout.addStretch(1)

  def sliceModified(self, caller, event):
    # if self._updatingSliceNodes:
    #   # prevent infinite loop of slice node updates triggering slice node updates
    #   return
    if self._updatingSephaloCorrectionValue:
      return
    self._updatingSliceNodes = True
    fov = caller.GetFieldOfView()[0]

    FOV = self.ui.FOVSelector.currentData
    if fov != FOV:
      self.ui.FOVSelector.setCurrentText(self.tr(""))
    self._updatingSliceNodes = False

  def _defaultIndustry3DPreset(self):
    """Get the default industry 3D rendering preset"""
    if self.industry == IndustryType.Medical:
      return self._vrLogic.GetPresetByName('プリセット1')
    return self._vrLogic.GetPresetByName('プリセット1')

  def _defaultIndustry2DPreset(self):
    """Get default 2D preset as configured in the UI without changing the current applied preset"""
    currentPreset = self.ui.preset2DSelector.currentText
    self.ui.preset2DSelector.setCurrentIndex(0)
    defaultPreset = self.ui.preset2DSelector.currentText
    self.ui.preset2DSelector.setCurrentText(currentPreset)
    return defaultPreset

  def setSlicerLayout(self, layoutType):
    self.ui.layoutSelector.setCurrentIndex(self.ui.layoutSelector.findData(layoutType))

  @wrapInQTimer
  def fitSlicesToBackground(self):
    for viewName in self._layoutManager.sliceViewNames():
      self._layoutManager.sliceWidget(viewName).fitSliceToBackground()

  def onLayoutSelect(self):
    if self._isLoadingState:
      return

    newLayout = self.ui.layoutSelector.currentData
    # Setup the layout before trying to get the viewNode, else, they won't exist
    layoutType = self.ui.layoutSelector.currentData
    
    # if layoutType > RFLayoutType.RFPanoramaLayout:
    #   layoutType = RFLayoutType.RFMainAxialLayout
    
    #self._layoutManager.setLayout(layoutType)
    
    #タブビュー機能追加　タブレイアウトへ各レイアウト設定の入れ込み
    layoutManager = slicer.app.layoutManager()
    mainLayout = layoutManager.layoutLogic().GetLayoutNode().GetLayoutDescription(self.ui.layoutSelector.currentData)
    tileLayout = ""
    
    if slicer.util.mainWindow().CentralWidget.CentralWidgetLayoutFrame.findChild("QTabBar"):
      #TileTabBarOn
      if slicer.util.mainWindow().CentralWidget.CentralWidgetLayoutFrame.findChild("QTabBar").isTabEnabled(1):
        TileLayoutNum = self.ui.numCombo.currentData
        tileLayout = layoutManager.layoutLogic().GetLayoutNode().GetLayoutDescription(RFLayoutType.RFTileLayout2x2 + TileLayoutNum)
      #panoramicTabBarOn #パノラミック時に追加予定
      #if  = slicer.util.mainWindow().CentralWidget.CentralWidgetLayoutFrame.findChild("QTabBar").isTabEnabled(2):
    
    slicer.modules.RFViewerHomeWidget.centralWidgetLayout(mainLayout,tileLayout,"",0)
    #-------------------------------------------
    
    if newLayout == RFLayoutType.RFTriple3D or newLayout == RFLayoutType.RFDual3D:
      self.setVRMode(self._currentVRMode)
      views = getAll3DViewNodes()
      for view in views:
        self.getVolumeDisplayNode3D().AddViewNodeID(view.GetID())
        layoutBackgroundSetup(view)

    # Apply slab thickness on new slice views
    self.onSlabThicknessSliderChanged()
    
    #lm = slicer.app.layoutManager()
    #if newLayout == RFLayoutType.RF2X2Layout:
    #  lm.sliceWidget("Red").sliceController().setLightbox(2, 2)
    #elif newLayout == RFLayoutType.RF3X3Layout:
    #  lm.sliceWidget("Red").sliceController().setLightbox(3, 3)
    #elif newLayout == RFLayoutType.RF4X4Layout:
    #  lm.sliceWidget("Red").sliceController().setLightbox(4, 4)
    #elif newLayout == RFLayoutType.RF5X5Layout:
    #  lm.sliceWidget("Red").sliceController().setLightbox(5, 5)
    #else:
    #  lm.sliceWidget("Red").sliceController().setLightbox(1, 1)
    # if newLayout == RFLayoutType.RF6X6Layout:
    #   lm.sliceWidget("Red").sliceController().setLightbox(6, 6)
    # if newLayout == RFLayoutType.RF7X7Layout:
    #   lm.sliceWidget("Red").sliceController().setLightbox(7, 7)
    # if newLayout == RFLayoutType.RF8X8Layout:
    #   lm.sliceWidget("Red").sliceController().setLightbox(8, 8)

  def onPreset3DSelect(self):
    if self._isLoadingState:
      return

    self._currentPreset3D = self.ui.preset3DSelector.currentNode()
    self.setPreset3D(self._currentPreset3D)

  def onPreset2DSelect(self):
    if self._isLoadingState:
      return

    self._currentPreset2D = self.ui.preset2DSelector.currentText
    self.setPreset2D(self._currentPreset2D)

  def onVRModeSelect(self):
    if self._isLoadingState:
      return

    self._currentVRMode = self.ui.vrModeSelector.currentData
    self.setVRMode(self._currentVRMode)

  def onColorSelect(self):
    if self._isLoadingState:
      return

    self._currentColor = self.ui.colorSelector.currentData
    self.setColorTo3D(self._currentColor)

  def onShiftSliderChanged(self):
    if self._isLoadingState:
      return

    if self._currentPreset3D is None:
      return

    newPosition = self.ui.shiftSlider.value
    self.ui.scalarMappingWidget.moveAllPoints(newPosition - self._previousThresholdPreset, 0., False)
    self._previousThresholdPreset = newPosition

  def onSlabThicknessSliderChanged(self):
    if self._isLoadingState:
      return
    volxstr = qt.QSettings().value("volx")
    if volxstr is None:
      volx = 100
    else:
      volx = int(qt.QSettings().value("volx"))
    if volx > 0:
      self.ui.slabThicknessSlider.setMaximum(volx)
    thickness = self.ui.slabThicknessSlider.value
    self.ui.setMIPThickness(thickness)
    return

    self.ui.thicknessText.setText(str(thickness) + " mm")

    data = self.ui.raycastSelector.currentData
    mode = vtk.VTK_IMAGE_SLAB_MAX
    if data == 1:
      mode = vtk.VTK_IMAGE_SLAB_MAX
    elif data == 2:
      mode = vtk.VTK_IMAGE_SLAB_MEAN
    else:
      mode = vtk.VTK_IMAGE_SLAB_SUM

    sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
    for slice in sliceNodes:
      slice.SetSlabMode(mode)
      #   slice.SetSlabMode(vtk.VTK_IMAGE_SLAB_SUM)
      #   slice.SetSlabMode(vtk.VTK_IMAGE_SLAB_MEAN)
      slice.SetSlabNumberOfSlices(thickness)
      slice.SetMipThickness(thickness)

  def onSynchronizeChanged(self):
    if self._isLoadingState:
      return

    self._synchronizeViews = self.ui.synchronizeCheckbox.checked
    self.ui.preset2DSelector.enabled = not self._synchronizeViews
    if not self.volumeNode:
      return

    if self._synchronizeViews and self.volumeNode.GetScalarVolumeDisplayNode():
      self.volumeNode.GetScalarVolumeDisplayNode().AutoWindowLevelOn()
      self.setColorTo2D(self._currentColor)
    else:
      self.setPreset2D(self._currentPreset2D)

  def onMIPThicknessChanged(self):
    if self._isLoadingState:
      return
    
    thickness = self.ui.thicknessSelector.currentData
    
    #--- 断層厚の厚さ修正--- 20221227 
    #ボクセルピッチの取得　X軸のピッチを使用
    volumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
    if not volumeNode:
      volume_spacing = (0.1, 0.1, 0.1)
    else:
      volume_spacing = volumeNode.GetSpacing()
    
    #ボクセル数変換
    vol_convert = (thickness / volume_spacing[0])#スライドバーはボクセル数単位の為、ｍｍ変換
    
    self.ui.slabThicknessSlider.setValue(int(vol_convert))
    
    self.ui.setMIPThickness(int(vol_convert))


  def onRaycastChanged(self):
    if self._isLoadingState:
      return
    
    thickness = self.ui.slabThicknessSlider.value
    self.ui.setMIPThickness(thickness)
    return
  def onROIDisplayed(self):
    checkVal = self.ui.displayROICheckBox.checked
    # 有効化の順序が重要。transform -> roiとすれば、重畳したNodeに対するUI上での操作は先に登録された順となるのでtransformにて通知が飛ぶ。
    self.ui.transform_display_node.SetEditorVisibility(checkVal)
    ROICropDisplayCheckVBox = slicer.util.findChild(self.ui.volumeRenderingWidget, "ROICropDisplayCheckBox")
    ROICropDisplayCheckVBox.setChecked(checkVal)
    if checkVal:
      ROICropDisplayCheckVBox.setChecked(False)

  def onResliceCursorDisplayed(self):
    if self._isLoadingState:
      return

    self._displayResliceCursor = self.ui.displayResliceCursorCheckbox.checked

    # Set 2D views
    views = slicer.util.getNodesByClass('vtkMRMLSliceCompositeNode')
    for view in views:
      view.SetSliceIntersectionVisibility(self._displayResliceCursor)

    # Set 3D view
    sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
    for slice in sliceNodes:
      slice.SetWidgetVisible(self._displayResliceCursor)

  def onTileOrientationChanged(self):
    if self._isLoadingState:
      return
    #setSliceOrientation()
    index = self.ui.directionCombo.currentData

    orientationList = ["Axial", "Sagittal", "Coronal"]
    orientation = orientationList[index]
    for i in range(1, 17):
      compare = slicer.app.layoutManager().sliceWidget('Compare' + str(i))
      compare.setSliceOrientation(orientation)

  def onTileIntervalSliderChanged(self):
    if self._isLoadingState:
      return

    compare = slicer.app.layoutManager().sliceWidget('Compare1')
    logic = compare.sliceLogic()
    interval = self.ui.sliceIntervalSlider.value

    self.ui.sliceIntervalText.setText(str(interval) + " mm")
    offset = logic.GetSliceOffset()
    for i in range(2, 17):
      offset = offset + interval
      compare = slicer.app.layoutManager().sliceWidget('Compare' + str(i))
      logic = compare.sliceLogic()
      logic.SetSliceOffset(offset)

  def onTileIntervalSelectorChanged(self):
    if self._isLoadingState:
      return
    
    interval = self.ui.sliceIntervalSelector.currentData
    self.ui.sliceIntervalSlider.setValue(interval)

  def onTilePositionSliderChanged(self):
    if self._isLoadingState:
      return

    compare = slicer.app.layoutManager().sliceWidget('Compare1')
    logic = compare.sliceLogic()
    posOffset = self.ui.slicePositionSlider.value

    logic.SetSliceOffset(posOffset)
    offset = logic.GetSliceOffset()
    interval = self.ui.sliceIntervalSlider.value
    for i in range(2, 17):
      offset = offset + interval
      compare = slicer.app.layoutManager().sliceWidget('Compare' + str(i))
      logic = compare.sliceLogic()
      logic.SetSliceOffset(offset)



  def onTilePositionSelectorChanged(self):
    if self._isLoadingState:
      return
    
    offset = self.ui.sliceIntervalSelector.currentData
    self.ui.slicePositionSlider.setValue(offset)

  def onTileLayoutChanged(self):
    if self._isLoadingState:
      return

    #タブビュー機能追加　タブレイアウトへ各レイアウト設定の入れ込み
    layoutManager = slicer.app.layoutManager()
    
    TileLayoutNum = self.ui.numCombo.currentData
    tileLayout = layoutManager.layoutLogic().GetLayoutNode().GetLayoutDescription(RFLayoutType.RFTileLayout2x2 + TileLayoutNum)
    
    slicer.modules.RFViewerHomeWidget.centralWidgetLayout("",tileLayout,"",1)
    #-------------------------------------------
 
  #--- for cephalometric 20220924 koyanagi --- add
  def onFOVChanged(self):
    # セファロ用の拡大率補正用コンボボックスの値の反映
    if self._isLoadingState:
      return
    #全断層画像（スライスビュー）のFOVへコンボボックスの値を反映
    FOV = self.ui.FOVSelector.currentData
    if FOV == 0:
      return
    layoutManager = slicer.app.layoutManager()
    self._updatingSephaloCorrectionValue = True
    for sliceViewName in layoutManager.sliceViewNames():
      sliceWidget = layoutManager.sliceWidget(sliceViewName).sliceLogic()
      sliceWidget.FitFOVToBackground(FOV)
    self._updatingSephaloCorrectionValue = False
  #-------------------------------------------

  #--- for cephalometric 20220924 koyanagi --- add
  def onOrientationMarkerChanged(self):
    if self._isLoadingState:
      return
    # Show/hide OrientationMarker
    self._OrientationMarkerVisibility = self.ui.OrientationMarkerCheckBox.checked
    viewNodes = slicer.util.getNodesByClass("vtkMRMLAbstractViewNode")
    if self._OrientationMarkerVisibility:
      OrientationMarkerType = slicer.vtkMRMLSliceNode.OrientationMarkerTypeCube
    else:
      OrientationMarkerType = 3 #OrientationMarkerTypeNoneコメントアウトされている。。。 あとで本体を修正
    for viewNode in viewNodes:
        viewNode.SetOrientationMarkerType(OrientationMarkerType)
  #-------------------------------------------

  #--- for cephalometric 20220924 koyanagi --- add
  def onRulerChanged(self):
    if self._isLoadingState:
      return
  	# Show/hide ruler
    self._RulerVisibility = self.ui.rulerCheckBox.checked
    viewNodes = slicer.util.getNodesByClass("vtkMRMLAbstractViewNode")
    if self._RulerVisibility:
      RulerType = 1 #Thin #---ルーラー非表示対応--- 20230105 Yao-sama
    else:
      RulerType = 0 #None #---ルーラー非表示対応--- 20230105 Yao-sama
    for viewNode in viewNodes:
        viewNode.SetRulerType(RulerType) # SetRulerType 本当はこっち
  #-------------------------------------------

  #--- for cephalometric & Speed up 20220924 koyanagi --- add
  def onFractionChanged(self):
    if self._isLoadingState:
      return
    # FractionSetting 断層厚の高速化
    self._FractionSetting = self.ui.fractionCheckBox.checked
    sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
    if self._FractionSetting:
      Fraction = 7 #暫定
    else:
      Fraction = 1
    for slice in sliceNodes:
      appLogic = slicer.app.applicationLogic()
      sliceLogic = appLogic.GetSliceLogic(slice)
      sliceLayerLogic = sliceLogic.GetBackgroundLayer()
      reslice = sliceLayerLogic.GetReslice()
      reslice.SetSlabSliceSpacingFraction(Fraction) 
      slice.Modified()

    thickness = self.ui.slabThicknessSlider.value
    self.ui.setMIPThickness(thickness)
  #-------------------------------------------

  def setPreset3D(self, preset):
    if self._isLoadingState:
      self._currentPreset3D = preset
      self.resetOffsetSlider()
      return

    displayNode3D = self.getVolumeDisplayNode3D()
    if displayNode3D is None:
      return

    displayNode3D.SetVisibility(True)
    displayNode3D.GetVolumePropertyNode().Copy(preset)
    self.resetOffsetSlider()
    self.ui.colorSelector.setCurrentIndex(0)
    if self._synchronizeViews:
      self.setColorTo2D(self._currentColor)

  def setPreset2D(self, presetName):
    """
    Set the correct 2D preset according to the preset name
    cf qSlicerScalarVolumeDisplayWidget::setPreset
    """
    if self._isLoadingState:
      self._currentPreset2D = presetName
      return

    if self.volumeNode is None:
      return

    displayNode = self.volumeNode.GetScalarVolumeDisplayNode()
    if not displayNode:
      return

    colorNodeID = ""
    window = -1
    level = 0
    if presetName == "CT-Bone":
      colorNodeID = "vtkMRMLColorTableNodeGrey"
      window = 1000
      level = 400
    elif presetName == "CT-Air":
      colorNodeID = "vtkMRMLColorTableNodeGrey"
      window = 1000
      level = -426
    elif presetName == "PET":
      colorNodeID = "vtkMRMLColorTableNodeRainbow"
      window = 10000
      level = 6000
    elif presetName == "CT-Abdomen":
      colorNodeID = "vtkMRMLColorTableNodeGrey"
      window = 350
      level = 40
    elif presetName == "CT-Brain":
      colorNodeID = "vtkMRMLColorTableNodeGrey"
      window = 100
      level = 50
    elif presetName == "CT-Lung":
      colorNodeID = "vtkMRMLColorTableNodeGrey"
      window = 1400
      level = 0.5
    elif presetName == "DTI":
      colorNodeID = "vtkMRMLColorTableNodeRainbow"
      window = 1
      level = 0.5

    if colorNodeID != "":
      displayNode.SetAndObserveColorNodeID(colorNodeID)

    if window != -1 or level != 0:
      displayNode.AutoWindowLevelOff()

    # cf qMRMLWindowLevelWidget
    if window != -1 and level != 0:
      displayNode.SetWindowLevel(window, level)
    elif window != -1:
      displayNode.SetWindow(window)
    elif level != 0:
      displayNode.SetLevel(level)
    self.ui.windowLevelWidget.pushButton1.click()
  def setVRMode(self, VRMode):
    if self._isLoadingState:
      self._currentVRMode = VRMode
      return

    views = getAll3DViewNodes()
    for view in views:
      view.SetRaycastTechnique(VRMode)

  def setColorTo3D(self, colorPreset):
    displayNode3D = self.getVolumeDisplayNode3D()
    if displayNode3D is None:
      return

    if self._isLoadingState:
      self._currentColor = colorPreset
      self.ui.scalarMappingWidget.setMRMLVolumePropertyNode(displayNode3D.GetVolumePropertyNode())
      return

    if colorPreset is None:
      self.setPreset3D(self._currentPreset3D)
    else:
      rangeCT = [0] * 2
      displayNode3D.GetVolumePropertyNode().GetColor().GetRange(rangeCT)
      colorTransferFunction = createDiscretizableColorTransferFunctionFromColorPreset(colorPreset, rangeCT)

      # only update color in order to keep the opacity
      displayNode3D.GetVolumePropertyNode().SetColor(colorTransferFunction)
      self.ui.scalarMappingWidget.setMRMLVolumePropertyNode(displayNode3D.GetVolumePropertyNode())

    if self._synchronizeViews:
      self.setColorTo2D(self._currentColor)

  def setColorTo2D(self, color):
    if self._isLoadingState:
      return

    if color is None:
      preset3DName = self._currentPreset3D.GetName()
      displayNode3D = self.getVolumeDisplayNode3D()
      if preset3DName not in self._map3DColorToColorTableNode and displayNode3D is not None:
        self._map3DColorToColorTableNode[preset3DName] = createColorNodeFromVolumePropertyNode(displayNode3D.GetVolumePropertyNode())
      currentColorID = self._map3DColorToColorTableNode[preset3DName].GetID()
    else:
      currentColorID = slicer.modules.colors.logic().GetColorTableNodeID(color)

    if self.volumeNode.GetScalarVolumeDisplayNode():
      self.volumeNode.GetScalarVolumeDisplayNode().SetAndObserveColorNodeID(currentColorID)

  def resetOffsetSlider(self):
    """
    cf qSlicerVolumeRenderingPresetComboBox::updatePresetSliderRange()
    """
    self._previousThresholdPreset = 0.0
    self.ui.shiftSlider.value = 0.0

    volumePropertyNode = self.getVolumeDisplayNode3D().GetVolumePropertyNode()
    volumePropertyNode.CalculateEffectiveRange()
    effectiveRange = volumePropertyNode.GetEffectiveRange()
    transferFunctionWidth = effectiveRange[1] - effectiveRange[0]

    self.ui.shiftSlider.minimum = -transferFunctionWidth * 2
    self.ui.shiftSlider.maximum = transferFunctionWidth * 2
    self.ui.shiftSlider.singleStep = closestPowerOfTen(transferFunctionWidth) / 500.0
    self.ui.shiftSlider.pageStep = self.ui.shiftSlider.singleStep

  def onSessionAboutToBeSaved(self):
    """Override from RFViewerWidget"""
    #---- セファロ用設定の復元 20230124 koyanagi -------------
    #間引き化の設定を読み込めない為、一旦チェックを外して保存
    if self.ui.fractionCheckBox.checked:
    	self.ui.fractionCheckBox.setChecked(False)
    #----------------------------------------------------------
    parameter = self.getParameterNode()
    parameter.SetParameter("VolumeNodeID", self.volumeNode.GetID())
    self.saveState()

  def saveState(self):
    """Override from RFViewerWidget"""
    parameter = self.getParameterNode()
    parameter.SetParameter("CurrentPreset2D", self._currentPreset2D)
    parameter.SetParameter("CurrentPreset3D", self._currentPreset3D.GetName())
    parameter.SetParameter("CurrentVRMode", str(self._currentVRMode))
    parameter.SetParameter("CurrentColor", str(self._currentColor))
    parameter.SetParameter("CurrentLayout", str(self.ui.layoutSelector.currentIndex))
    parameter.SetParameter("CurrentThreshold", str(self._previousThresholdPreset))
    parameter.SetParameter("IndustryType", str(self.industry.value))

  def onSessionLoaded(self):
    """Override from RFViewerWidget"""
    # Load presets from parameters
    parameter = self.getParameterNode()

    # Set the volume node
    self._isLoadingState = True
    self.setVolumeNode(slicer.mrmlScene.GetNodeByID(parameter.GetParameter("VolumeNodeID")))
    self.applyState()
    self._isLoadingState = False
    self._refresh3DView()
    #---- セファロ用設定の復元 20230124 koyanagi -------------
    self._restoreCephalo_Setting()
    #-----------------------------------------------------------

  def applyState(self):
    """Override from RFViewerWidget"""
    oldLoadingState = self._isLoadingState
    self._isLoadingState = True
    parameter = self.getParameterNode()

    # Apply layout
    self.ui.layoutSelector.setCurrentIndex(int(parameter.GetParameter("CurrentLayout")))

    # Get correct 2D and 3D presets
    industry = IndustryType(int(parameter.GetParameter("IndustryType")))
    if industry == self.industry:
      preset3D = self._vrLogic.GetPresetByName(parameter.GetParameter("CurrentPreset3D"))
      preset2D = parameter.GetParameter("CurrentPreset2D")
    else:
      warningMessageBox(self.tr("Loading from different industry type"), self.tr(
        "Session was saved with a different industry type. It will be loaded using current default industry type presets."))
      preset3D = self._defaultIndustry3DPreset()
      preset2D = self._defaultIndustry2DPreset()

    # Apply 3D preset
    self.ui.preset3DSelector.setCurrentNode(preset3D)

    # Apply color
    try:
      self._selectItemWithInputData(self.ui.colorSelector, int(parameter.GetParameter("CurrentColor")))
    except ValueError:  # Default 3D preset color
      self.ui.colorSelector.setCurrentIndex(0)

    # Apply threshold
    self.ui.shiftSlider.value = float(parameter.GetParameter("CurrentThreshold"))

    # Apply 2D preset
    self.ui.preset2DSelector.setCurrentText(preset2D)

    # Apply VRMode
    self._selectItemWithInputData(self.ui.vrModeSelector, int(parameter.GetParameter("CurrentVRMode")))
    self._isLoadingState = oldLoadingState

  @staticmethod
  def _selectItemWithInputData(selector, data):
    """
    Set selector index to the first item which has the input data value.
    """
    for i in range(selector.count):
      if selector.itemData(i) == data:
        selector.setCurrentIndex(i)
        break

  def _refresh3DView(self):
    """
    3D View volume rendering may not show on loading when other models are visible on integrated graphics cards.
    Disable the visibility of every model to enable VR loading and reactivate the visibility.
    """

    # Get display element states
    self._displayNodeVisibility = {d: d.GetVisibility3D() for d in slicer.mrmlScene.GetNodes() if
                                   isinstance(d, slicer.vtkMRMLDisplayNode)}
    self._roisVisibility = {r: r.GetDisplayVisibility() for r in
                            list(slicer.mrmlScene.GetNodesByClass('vtkMRMLAnnotationROINode'))}
    self._viewVisibility = {v: v.GetWidgetVisible() for v in list(slicer.util.getNodesByClass('vtkMRMLSliceNode'))}

    # Disable visibility everywhere
    self._disable3DVisibility()

    # Enable visibility for the VR only
    self.getVolumeDisplayNode3D().SetVisibility3D(True)

    # Restore visibility (wrapped in QTimer to execute after VR only is displayed)
    qt.QTimer.singleShot(0, self._restore3DVisibility)

  def _restore3DVisibility(self, forcedVisibilityValue=None):
    """
    Restores visibility for the three input visibility dictionaries if forcedVisibilityValue is None
    Otherwise forces the visibility to the given input visibility value
    """

    def isVisible(state):
      return state if forcedVisibilityValue is None else forcedVisibilityValue

    for d, previous_state in self._displayNodeVisibility.items():
      d.SetVisibility3D(isVisible(previous_state))

    for r, previous_state in self._roisVisibility.items():
      r.SetDisplayVisibility(isVisible(previous_state))

    for v, previous_state in self._viewVisibility.items():
      v.SetWidgetVisible(isVisible(previous_state))

  def _disable3DVisibility(self):
    self._restore3DVisibility(forcedVisibilityValue=False)

  #---- セファロ用設定の復元 20230124 koyanagi -------------
  def _restoreCephalo_Setting(self):
    """
    For restoring settings for cephalometric
    """
    #--- スライスの表示設定の読み込み ---
    sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
    cnt = 0
    for slice in sliceNodes:
      self._SlabMode_Setting[cnt] = slice.GetSlabMode()#投影方法
      self._NumberOfSlices_Setting[cnt] = slice.GetSlabNumberOfSlices()#枚数
      cnt = cnt + 1
    #--- スラブモードの設定　（最初のノードの設定に合わせる）---
    if self._SlabMode_Setting[0] == vtk.VTK_IMAGE_SLAB_MAX:
      mode_index = 0
      #print("SlabMode_Setting MAX")
    elif self._SlabMode_Setting[0] == vtk.VTK_IMAGE_SLAB_MEAN:
      mode_index = 1
      #print("SlabMode_Setting MEAN")
    elif self._SlabMode_Setting[0] == vtk.VTK_IMAGE_SLAB_MIN:
      mode_index = 2
      #print("SlabMode_Setting MIN")
    else:
      mode_index = 0
      #print("SlabMode_Setting unknown")
    #セレクタの更新
    self.ui.raycastSelector.setCurrentIndex(mode_index)
    #--- 断層厚の設定　（最初のノードの設定に合わせる）---
    # Apply slab thickness on new slice views　スライドバーの最大値の更新
    self.onSlabThicknessSliderChanged()
    #　断層厚の値の更新
    self.ui.slabThicknessSlider.setValue(self._NumberOfSlices_Setting[0])
    self.ui.setMIPThickness(self._NumberOfSlices_Setting[0])
    #print("_NumberOfSlices_Setting",self._NumberOfSlices_Setting[0])
