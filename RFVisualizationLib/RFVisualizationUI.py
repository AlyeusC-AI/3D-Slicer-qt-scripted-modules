from logging import NullHandler
import ctk
import qt
import slicer, vtk, numpy
from enum import unique, Enum
from RFReconstruction import RFReconstructionLogic


from RFViewerHomeLib import translatable, toggleCheckBox, createButton, getNodeByID
from RFVisualizationLib import RFLayoutType

@unique
class IndustryType(Enum):
  Medical = 0
  Dental = 1


@translatable
class RFVisualizationUI(qt.QStackedWidget):

  def __init__(self, vrLogic, preset, industryType):
    qt.QStackedWidget.__init__(self)

    self._normalWidget = qt.QWidget()
    self._tileWidget = qt.QWidget()
    self._layout = qt.QFormLayout()
    self._tileLayout = qt.QFormLayout() #表示設定部位
    #---レイアウト変更--- 20221227 koyanagi
    # スペース削減とレイアウト順変更
    self._layout.setMargin(3)#マージン削減
    self._layout.setVerticalSpacing(3)#スペース削減
    self.spacing = 0 #スペース削減
    self.industry = industryType
    self.isCephalo = False
    self.addLayoutSection()
    self.add3DSection(vrLogic, preset)
    self.add2DSection()
    self.addCropSection()
    self.addIntermediateSection()
    self.addMagnificationSection()
    self.addAdvancedSection()

    self.customMouseAction3D()
    self.customMouseAction2D()

    self.createTileUILayout()
    self._normalWidget.setLayout(self._layout)
    self._tileWidget.setLayout(self._tileLayout)

    self.addWidget(self._normalWidget)
    self.addWidget(self._tileWidget)
    self.setCurrentIndex(0)


  def setVolumeNode(self, volumeNode, displayNode3D, isLoadingState):
    # Select volume in VolumeRenderingWidget selector for volume cropping and deactivate previous cropping settings
    self._volumeSelector.setCurrentNode(volumeNode)

    # Create TransformNode & vtkTransform for rotating VolumeNode.
    vol_rotate_transform_node_id = volumeNode.GetTransformNodeID()
    if not vol_rotate_transform_node_id:
      vol_rotate_transform_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode")
      vol_rotate_transform_node_id = vol_rotate_transform_node.GetID()
      translate = vtk.vtkTransform()
      vol_rotate_transform_node.SetAndObserveTransformToParent(translate)
      volumeNode.SetAndObserveTransformNodeID(vol_rotate_transform_node_id)

    # Create ROI for the current display node if it doesn't exist (avoids crop volume logic crash)
    roi_node = displayNode3D.GetROINode()
    if not roi_node:
      roi_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLAnnotationROINode")
      roi_node.SetInteractiveMode(1)
      displayNode3D.SetAndObserveROINodeID(roi_node.GetID())

    roi_transform_node_id = roi_node.GetTransformNodeID()
    if roi_transform_node_id:
      self._transform_node = slicer.mrmlScene.GetNodeByID(roi_node.GetTransformNodeID())
      self.transform_display_node = slicer.mrmlScene.GetNodeByID(self._transform_node.GetDisplayNodeID())
      self._transform_node.SetAndObserveDisplayNodeID(self.transform_display_node.GetID())
      roi_node.SetAndObserveTransformNodeID(roi_transform_node_id)
    else:
      self._transform_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode")
      self.transform_display_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTransformDisplayNode")
      self.transform_display_node.SetEditorTranslationEnabled(True)
      self.transform_display_node.SetEditorRotationEnabled(True)
      self.transform_display_node.SetEditorScalingEnabled(True)
      self._transform_node.SetAndObserveDisplayNodeID(self.transform_display_node.GetID())
      roi_node.SetAndObserveTransformNodeID(self._transform_node.GetID())

    self._transform_node.SetAndObserveTransformNodeID(vol_rotate_transform_node_id)
    self.transform_display_node.UpdateEditorBounds()

    # Deactivate checkboxes (and toggle them) to make sure the parameter is correctly applied
    # When loading a session, if the checkbox status are not toggled, the correct check status may be selected but not
    # propagated to the volume
    for checkBox in [self._cropCheckBox, self.displayROICheckBox, self.displayResliceCursorCheckbox,
                     self.synchronizeCheckbox]:
      toggleCheckBox(checkBox, lastCheckedState=False)

    # set default value for reloading
    toggleCheckBox(self.rulerCheckBox, lastCheckedState=True)
    toggleCheckBox(self.OrientationMarkerCheckBox, lastCheckedState=True)
    toggleCheckBox(self.fractionCheckBox, lastCheckedState=False)
    self.FOVSelector.setCurrentText(self.tr(""))
    self.raycastSelector.setCurrentText(self.tr("Ray Max"))

    # Fit Volume ROI to volume (by default ROI is 0)
    if not isLoadingState:
      #これでROI初期化実現している
      self._ROIFitPushButton.click()
      self.transform_display_node.UpdateEditorBounds()

    # Set window level and scalar mapping widgets input nodes
    self.windowLevelWidget.setMRMLVolumeNode(volumeNode)
    self.scalarMappingWidget.setMRMLVolumePropertyNode(displayNode3D.GetVolumePropertyNode() if displayNode3D else None)

  def createTileUILayout(self): 
    #alignment.
    self._tileLayout.setVerticalSpacing(2)
    self._tileLayout.setHorizontalSpacing(0)

    #1
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("方位")))
    directionCombo = qt.QComboBox()
    directionCombo.setToolTip(self.tr("Select the 方位"))
    directionCombo.addItem("Axial", 1)
    directionCombo.addItem("Sagital", 2)
    directionCombo.addItem("Coronal", 3)
    directionCombo.setCurrentIndex(0)
    layoutPre.addWidget(directionCombo)

    #2
    layoutPre.addWidget(self._createLabel(self.tr("表示枚数")))
    numCombo = qt.QComboBox()
    numCombo.setToolTip(self.tr("Select the number"))
    numCombo.addItem("2x2", 1)
    numCombo.addItem("3x3", 2)
    numCombo.addItem("4x4", 3)
    numCombo.setCurrentIndex(0)
    layoutPre.addWidget(numCombo)
    self._tileLayout.addRow(layoutPre)
 
    #3
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self.windowLevelWidget)
    self._tileLayout.addRow(layoutPre)

    #5
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("投影法")))
    self.raycastSelector = self.createRaycastCombobox()#レイキャストコンボボックス
    layoutPre.addWidget(self.raycastSelector,0,1)
    self._tileLayout.addRow(layoutPre)
 
    #6
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("間隔")))
    self._tileLayout.addRow(layoutPre)
    #7
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("位置")))
    self._tileLayout.addRow(layoutPre)
    #8
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("")))
    self.OrientationMarkerCheckBox = qt.QCheckBox(self.tr("マーカー"))
    self.OrientationMarkerCheckBox.setToolTip(self.tr("マーカーの表示・非表示設定"))
    toggleCheckBox(self.OrientationMarkerCheckBox, lastCheckedState=True)
    layoutPre.addWidget(self.OrientationMarkerCheckBox)
    
  	#ルーラーのチェックボックス
    self.rulerCheckBox = qt.QCheckBox(self.tr("ルーラー"))
    self.rulerCheckBox.setToolTip(self.tr("ルーラーの表示・非表示設定"))
    toggleCheckBox(self.rulerCheckBox, lastCheckedState=True)
    layoutPre.addWidget(self.rulerCheckBox)
    self._tileLayout.addRow(layoutPre)

    #9
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("")))
    self._tileLayout.addRow(layoutPre)

  def addLayoutSection(self):
    self.layoutSection = qt.QFormLayout()
    self.setLayoutSpacing(self.layoutSection)
    #---レイアウト変更--- 20221227 koyanagi
    self.layoutSection.setVerticalSpacing(2)
    self.layoutSection.setHorizontalSpacing(0)
    
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("レイアウト")))#self.tr("Layout: ")
    self.layoutSelector = self.createLayoutComboBox()
    layoutPre.addWidget(self.layoutSelector)
    self._layout.addRow(layoutPre)

  def add3DSection(self, vrLogic, preset):
    self.layout3D = qt.QFormLayout()
    self.setLayoutSpacing(self.layout3D)
    #---レイアウト変更--- 20221227 koyanagi
    self.layout3D.setVerticalSpacing(2)
    self.layout3D.setHorizontalSpacing(0)

    #ライン挿入
    self.layout3D.addRow(self._createSeparator())
  	#3Dプリセットのレイアウト
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("３Ｄ")))
    layoutPre.addWidget(self._createLabel(self.tr("プリセット")))#self.tr("Presets 3D: ")
    self.preset3DSelector = self.createPresetComboBox(vrLogic, preset)
    layoutPre.addWidget(self.preset3DSelector)
    self.layout3D.addRow(layoutPre)
    
  	#3Dレベルのレイアウト
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("")))
    layoutPre.addWidget(self._createLabel(self.tr("レベル"))) #self.tr("Threshold VR: ")
    self.shiftSlider = self.createShiftPresetSlider()
    layoutPre.addWidget(self.shiftSlider)
    self.layout3D.addRow(layoutPre)
    
    #未使用
    self.colorSelector = self.createLookupTableComboBox()
    # self.layout3D.addRow(self.tr("Color Presets: "), self.colorSelector)
    self.vrModeSelector = self.createVolumeRenderingModeComboBox()
    # self.layout3D.addRow(self.tr("VR Mode: "), self.vrModeSelector)
    
    self._layout.addRow(self.layout3D)

  def add2DSection(self):
    self.layout2D = qt.QFormLayout()
    self.setLayoutSpacing(self.layout2D)
    #---レイアウト変更--- 20221227 koyanagi
    self.layout2D.setSpacing(2)
    self.layout2D.setVerticalSpacing(2)
    self.layout2D.setHorizontalSpacing(0)
    
    #ライン挿入
    self.layout2D.addRow(self._createSeparator())
  	#2Dレベルのレイアウト
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("２Ｄ")),0,0x20) #上寄せ
    layoutPre.addWidget(self._createLabel(self.tr("レベル")),0,0x20) #上寄せ self.tr("2D Window/Level: ")
    self.windowLevelWidget = self.createWindowLevelWidget()
    layoutPre.addWidget(self.windowLevelWidget)
    self.layout2D.addRow(layoutPre)
    
    #ライン挿入
    self.layout2D.addRow(self._createSeparator())
  	#断層厚のレイアウト１段目　厚み表示　断層厚のスライダー　コンボボックス
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("断層厚")))#self.tr("MIP thickness: ")
    self.thicknessText = qt.QLabel() #厚み表示
    self.thicknessText.setStyleSheet("QLabel {min-width: 50px; max-width: 50px;}")
    layoutPre.addWidget(self.thicknessText)
    self.slabThicknessSlider = self.createSlabThicknessSlider() #断層厚のスライダー
    layoutPre.addWidget(self.slabThicknessSlider)
    self.thicknessSelector = self.createMIPThicknessCombobox() #厚さのコンボボックス
    layoutPre.addWidget(self.thicknessSelector)
    self.layout2D.addRow(layoutPre)
    
  	#断層厚のレイアウト２段目
    layoutPre = qt.QHBoxLayout()
    
    layoutPre.addWidget(self._createLabel(self.tr("投影法")))
    self.raycastSelector = self.createRaycastCombobox()#レイキャストコンボボックス
    layoutPre.addWidget(self.raycastSelector,0,1)
    
    self.fractionCheckBox = qt.QCheckBox(self.tr("間引処理"))
    self.fractionCheckBox.setToolTip(self.tr("間引き表示の切り替え"))
    layoutPre.addWidget(self.fractionCheckBox)
    toggleCheckBox(self.fractionCheckBox, lastCheckedState=False)
    
    layoutPre.addWidget(qt.QLabel("")) #位置合わせにスペース追加
    layoutPre.addWidget(self._createLabel(self.tr(""))) #位置合わせにスペース追加
    self.layout2D.addRow(layoutPre)
    
    #未使用
    self.preset2DSelector = self.create2DPresetComboBox()
    # self.layout2D.addRow(self.tr("Presets 2D: "), self.preset2DSelector)
    
    self._layout.addRow(self.layout2D)

#ここでUICropBoxのUI作っている
  def addCropSection(self):
    #---レイアウト変更--- 20221227 koyanagi
    self.layoutCB = qt.QFormLayout()
    self.setLayoutSpacing(self.layoutCB)
    self.layoutCB.setVerticalSpacing(2)
    self.layoutCB.setHorizontalSpacing(0)

    #ライン挿入
    self.layoutCB.addRow(self._createSeparator())
    
  	#断層軸のチェックボックス
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("表示")))
    self.displayResliceCursorCheckbox = qt.QCheckBox(self.tr("断層軸"))
    layoutPre.addWidget(self.displayResliceCursorCheckbox)
    
    #スペース追加
    #layoutPre.addSpacing(10)
    
    self.displayROICheckBox = qt.QCheckBox(self.tr("ｸﾘｯﾋﾟﾝｸﾞ"))#self.tr("Display ROI")
    layoutPre.addWidget(self.displayROICheckBox)
    #スペース追加
    #layoutPre.addSpacing(10)
    self._fitToVolumeButton = qt.QPushButton(self.tr("リセット"))#self.tr("Fit to Volume")
    self._fitToVolumeButton.setToolTip(self.tr("クリップボックスの初期化"))
    self._fitToVolumeButton.setStyleSheet("QPushButton {margin: 1px;  min-width: 12px; padding-top: 3px; padding-bottom: 3px; padding-right: 1px; padding-left: 1px; spacing: 0;}")
    self._fitToVolumeButton.connect("clicked(bool)", self.fitToVolumeButton)
    layoutPre.addWidget(self._fitToVolumeButton)
    layoutPre.addWidget(self._createLabel(self.tr("　　　　"))) #位置合わせにスペース追加
    self.layoutCB.addRow(layoutPre)
    
    self._layout.addRow(self.layoutCB)
    
    self.volumeRenderingWidget = slicer.util.getNewModuleGui(slicer.modules.volumerendering)
    self._volumeSelector = slicer.util.findChild(self.volumeRenderingWidget, "VolumeNodeComboBox")
    
    self._cropCheckBox = slicer.util.findChild(self.volumeRenderingWidget, "ROICropCheckBox")
    self._cropCheckBox.text = self.tr("Enabled")
    
    self._ROIFitPushButton = slicer.util.findChild(self.volumeRenderingWidget, "ROIFitPushButton")
    
    #未使用
    self.synchronizeCheckbox = qt.QCheckBox()
    # self.layoutIntermediate.addRow(self.tr("Synchronize 2D/3D colors: "), self.synchronizeCheckbox)
    # layout.addWidget(qt.QLabel(self.tr("Crop:")))
    # layout.addWidget(self._cropCheckBox)
    #self._layout.addRow(layout)


  def addMagnificationSection(self):
    #---レイアウト変更--- 20221227 koyanagi
    # Layout of Cephalometric Tools for cephalometric
    self.layoutMagnification = qt.QFormLayout()
    self.setLayoutSpacing(self.layoutMagnification)
    self.layoutMagnification.setVerticalSpacing(2)
    self.layoutMagnification.setHorizontalSpacing(0)
    #ライン挿入
    self.layoutMagnification.addRow(self.layoutMagnification.setHorizontalSpacing(50), self._createSeparator())
  	#マーカーのチェックボックス
    layoutPre = qt.QHBoxLayout()
    layoutPre.addWidget(self._createLabel(self.tr("")))
    self.OrientationMarkerCheckBox = qt.QCheckBox(self.tr("マーカー"))
    self.OrientationMarkerCheckBox.setToolTip(self.tr("マーカーの表示・非表示設定"))
    toggleCheckBox(self.OrientationMarkerCheckBox, lastCheckedState=True)
    layoutPre.addWidget(self.OrientationMarkerCheckBox)
    
  	#ルーラーのチェックボックス
    self.rulerCheckBox = qt.QCheckBox(self.tr("ルーラー"))
    self.rulerCheckBox.setToolTip(self.tr("ルーラーの表示・非表示設定"))
    toggleCheckBox(self.rulerCheckBox, lastCheckedState=True)
    layoutPre.addWidget(self.rulerCheckBox)
    
    #セファロ補正値
    layoutPre.addWidget(self._createLabel(self.tr("拡大値")))
    self.FOVSelector = self.createFOVCombobox()
    layoutPre.addWidget(self.FOVSelector)
    
    #レイアウト
    self.layoutMagnification.addRow(layoutPre)
    self._layout.addRow(self.layoutMagnification)
    
    #元ソースのなごり　一旦残し
    self.setMIPThickness5Button()   # default thickness as 5, must be called after raycastSelector initialized
    #---- 断層厚の厚さ修正　20221021 ---
    #初期値設定
    self.slabThicknessSlider.setValue(0.5)
    self.setMIPThickness(5)
    

  def setMIPThickness(self, thickness):
    #--- 断層厚の厚さ修正--- 20221227 
    #ボクセルピッチの取得　X軸のピッチを使用
    volumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
    if not volumeNode:
      volume_spacing = (0.1, 0.1, 0.1)
    else:
      volume_spacing = volumeNode.GetSpacing()
    
    #mm変換
    mm_convert = (volume_spacing[0] * thickness)#スライドバーはボクセル数単位の為、ｍｍ変換
    
    #スライス厚の表示
    self.thicknessText.setText((f'{mm_convert:.1f}')+ " mm")#小数点１位まで表示
    
    #間引き化のチェックボックス確認
    if self.fractionCheckBox.isChecked():
      Fraction = 7 #間引き割合　ｎ枚に１枚
    else:
      Fraction = 1
    
    #スライス数変換
    NumberOfSlices = thickness/Fraction #ボクセル数からスライス数を変換
    if NumberOfSlices < 1:#最小値を１枚に設定
      NumberOfSlices = 1
    else:
      NumberOfSlices = NumberOfSlices + 1
    
    #投影方法の反映とスライスの反映
    sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
    data = self.raycastSelector.currentData
    mode = vtk.VTK_IMAGE_SLAB_MAX
    if data == 1:
      mode = vtk.VTK_IMAGE_SLAB_MAX
    elif data == 2:
      mode = vtk.VTK_IMAGE_SLAB_MEAN
    else:
      mode = vtk.VTK_IMAGE_SLAB_MIN
    
    for slice in sliceNodes:
      slice.SetSlabMode(mode)#投影方法
      slice.SetSlabNumberOfSlices(int(NumberOfSlices))#枚数入力
      slice.SetMipThickness(int(mm_convert))#mm入力
      slice.Modified()
    

  def fitToVolumeButton(self):
    # 変形は全てtransformで実施。ROIはtransformされるだけなのでtransformを初期化すればOK。
    identity_matrix = vtk.vtkMatrix4x4()
    self._transform_node.SetMatrixTransformToParent(identity_matrix)

  def setMIPThickness2Button(self):
    thickness = 2
    self.slabThicknessSlider.setValue(thickness)
    self.setMIPThickness(thickness)

  def setMIPThickness5Button(self):
    thickness = 5
    self.slabThicknessSlider.setValue(thickness)
    self.setMIPThickness(thickness)

  def setMIPThickness10Button(self):
    thickness = 10
    self.slabThicknessSlider.setValue(thickness)
    self.setMIPThickness(thickness)

  def toggleCephalometric(self, scale, set):
    # numVolumeNodes = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLVolumeNode')
    # for n in range(numVolumeNodes):
    #   volumeNode = slicer.mrmlScene.GetNthNodeByClass(n, 'vtkMRMLVolumeNode')

    #   matrix = vtk.vtkMatrix4x4() 
    #   matrix.SetElement(0, 0, scale)
    #   matrix.SetElement(1, 1, scale)
    #   # matrix.SetElement(2, 2, scale)
    #   # matrix.SetElement(3, 3, 1)

    #   volumeNode.ApplyTransformMatrix(matrix)
    lm = slicer.app.layoutManager()
    sliceNames = lm.sliceViewNames()

    for sliceName in sliceNames:
      sliceWidget = lm.sliceWidget(sliceName)
      sliceView = sliceWidget.sliceView()      
      if type(sliceView) == slicer.qMRMLSliceView:
        if set == 1:
            sliceView.setSliceZoom(scale)
        else:
            sliceView.clearSliceZoom()

  def setCephalometric(self):
    numVolumeNodes = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLVolumeNode')
    if numVolumeNodes < 1:
        return

    self.cephalometricButton.setEnabled(False)
    self.isCephalo = True
    self.toggleCephalometric(1.1, 1)

  def showMarkers(self):
    # nodes = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
    nodes = slicer.util.getNodesByClass("vtkMRMLMarkupsNode")
    numbers = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLMarkupsNode')
    # if len(nodes) > 0:
    #   markupNode = nodes[0]
    for n in range(numbers):
      # markupNode = slicer.mrmlScene.GetNthNodeByClass(n, 'vtkMRMLMarkupsNode')
      markupNode = nodes[n]
      nn = markupNode.GetNumberOfControlPoints()
      print("markup " + str(n))
      for k in range(nn):
        cp = [0, 0, 0]
        markupNode.GetNthControlPointPosition(k, cp)
        # cp = markupNode.GetNthControlPoint(k)
        # print(cp)

  def clearCephalometric(self):


    # if self.isCephalo == False:
    #     return
    self.cephalometricButton.setEnabled(True)
    self.isCephalo = False

    self.toggleCephalometric(1, 0)



  def addIntermediateSection(self):
    #---レイアウト変更--- 20221227 koyanagi
    """
    self.layoutIntermediate = qt.QFormLayout()
    self.setLayoutSpacing(self.layoutIntermediate)

    self.synchronizeCheckbox = qt.QCheckBox()
    # self.layoutIntermediate.addRow(self.tr("Synchronize 2D/3D colors: "), self.synchronizeCheckbox)

    self.displayResliceCursorCheckbox = qt.QCheckBox()
    self.layoutIntermediate.addRow(self.tr("Show MPR: "), self.displayResliceCursorCheckbox)

    self._layout.addRow(self.layoutIntermediate)
    """

  def addAdvancedSection(self):
    self.layoutAdvanced = qt.QFormLayout()
    self.setLayoutSpacing(self.layoutAdvanced)

    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = self.tr("Advanced")
    parametersCollapsibleButton.collapsed = True
    self.layoutAdvanced.addWidget(parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayoutAdvanced = qt.QFormLayout(parametersCollapsibleButton)
    parametersCollapsibleButton.hide()
    #
    # Color/opacity scalar mapping
    #
    self.scalarMappingWidget = slicer.qMRMLVolumePropertyNodeWidget()
    parametersFormLayoutAdvanced.addWidget(self.scalarMappingWidget)

    #self._layout.addRow(self.layoutAdvanced)

  def setLayoutSpacing(self, layout):
    layout.setHorizontalSpacing(self.spacing)

  def _addSeparator(self):
    separator = qt.QFrame()
    separator.setFrameShape(qt.QFrame.HLine)
    separator.setFrameShadow(qt.QFrame.Sunken)
    self._layout.addWidget(separator)

  def createLayoutComboBox(self):
    """
    Create a combobox to choose the display layout
    """
    selector = qt.QComboBox()
    selector.setToolTip(self.tr("Select the display .layout."))
    selector.addItem(self.tr("Four-up"), RFLayoutType.RFDefaultLayout)
    selector.addItem(self.tr("Main 3D"), RFLayoutType.RFMain3DLayout)
    selector.addItem(self.tr("Main Axial"), RFLayoutType.RFMainAxialLayout)
    selector.addItem(self.tr("Main Sagittal"), RFLayoutType.RFMainSagittalLayout)
    selector.addItem(self.tr("Main Coronal"), RFLayoutType.RFMainCoronalLayout)
    selector.addItem(self.tr("Conventional"), RFLayoutType.RFConventional)
    # selector.addItem(self.tr("Dual 3D"), RFLayoutType.RFDual3D)
    # selector.addItem(self.tr("Triple 3D"), RFLayoutType.RFTriple3D)
    selector.addItem(self.tr("3D Only"), RFLayoutType.RF3DOnly)
    selector.addItem(self.tr("Line Profile"), RFLayoutType.RFLineProfileLayout)
    #selector.addItem(self.tr("Panorama"), RFLayoutType.RFPanoramaLayout)
    #selector.addItem(self.tr("Axial Only"), RFLayoutType.RFAxialOnly)
    # selector.addItem(self.tr("2 x 2"), RFLayoutType.RF2X2Layout)
    # selector.addItem(self.tr("3 x 3"), RFLayoutType.RF3X3Layout)
    # selector.addItem(self.tr("4 x 4"), RFLayoutType.RF4X4Layout)
    # selector.addItem(self.tr("5 x 5"), RFLayoutType.RF5X5Layout)
    # selector.addItem(self.tr("6 x 6"), RFLayoutType.RF6X6Layout)
    # selector.addItem(self.tr("7 x 7"), RFLayoutType.RF7X7Layout)
    # selector.addItem(self.tr("8 x 8"), RFLayoutType.RF8X8Layout)
    selector.setCurrentText(self.tr("Main 3D"))
    #---レイアウト変更--- 20221227 koyanagi
    selector.setStyleSheet("""
        QComboBox QAbstractItemView {border: 2px solid darkgray; selection-background-color: lightgray;}
    	""")#レイアウト変更
    return selector

  def createPresetComboBox(self, vrLogic, currentPreset):
    """
    Create a slicer combobox to choose the preset
    that will be applied on the volume rendering
    """

    # define removable presets
    presetsToRemove = ["MR-Angio", "MR-Default", "MR-MIP", "MR-T2-Brain", "DTI-FA-Brain"]

    # if self.industry == IndustryType.Medical:
    #   presetsToRemove += ["CT-Soft-Tissue", "CT-Air"]
    # if self.industry == IndustryType.Dental:
    #   presetsToRemove += ["CT-AAA", "CT-AAA2", "CT-Bone", "CT-Bones", "CT-Cardiac", "CT-Cardiac2",
    #   "CT-Cardiac3", "CT-Chest-Contrast-Enhanced", "CT-Chest-Vessels", "CT-Coronary-Arteries",
    #   "CT-Coronary-Arteries-2", "CT-Coronary-Arteries-3", "CT-Cropped-Volume-Bone", "CT-Fat",
    #   "CT-Liver-Vasculature", "CT-Lung", "CT-MIP", "CT-Muscle", "CT-Pulmonary-Arteries"]

    for preset in presetsToRemove:
      presetNode = vrLogic.GetPresetByName(preset)
      vrLogic.RemovePreset(presetNode)

    selector = slicer.qSlicerPresetComboBox()
    selector.nodeTypes = ["vtkMRMLVolumePropertyNode"]
    selector.setMRMLScene(vrLogic.GetPresetsScene())
    selector.showIcons = False
    selector.setCurrentNode(currentPreset)
    #---レイアウト変更--- 20221227 koyanagi
    selector.setStyleSheet("""
        QComboBox QAbstractItemView {border: 2px solid darkgray; selection-background-color: lightgray;}
    	""")#レイアウト変更
    return selector

  def create2DPresetComboBox(self):
    selector = qt.QComboBox()
    selector.setToolTip(self.tr("Select the 2D preset."))
    if self.industry == IndustryType.Medical:
      selector.addItem("CT-Abdomen")
      selector.addItem("CT-Lung")
      selector.addItem("CT-Brain")
    elif self.industry == IndustryType.Dental:
      selector.addItem("CT-Bone")
      selector.addItem("CT-Air")
    selector.setCurrentIndex(0)
    return selector

  def createVolumeRenderingModeComboBox(self):
    """
    Create a combobox that will allow to choose the volume rendering
    visualization mode : Default or X-Ray
    """
    selector = qt.QComboBox()
    selector.setToolTip(self.tr("Select the visualization rendering mode"))
    selector.addItem(self.tr("Default VR"), slicer.vtkMRMLViewNode().Composite)
    selector.addItem(self.tr("X-Ray VR"), slicer.vtkMRMLViewNode().MaximumIntensityProjection)
    selector.setCurrentIndex(0)
    return selector

  def createLookupTableComboBox(self):
    """
    Create a combobox which lists the available lookup table
    that can be applied to the rendering
    """
    selector = qt.QComboBox()
    selector.setToolTip(self.tr("Select the color preset"))
    selector.addItem(self.tr("Current 3D preset color"), None)
    selector.addItem(self.tr("Grey"), slicer.vtkMRMLColorTableNode().Grey)
    selector.addItem(self.tr("Rainbow"), slicer.vtkMRMLColorTableNode().Rainbow)
    selector.addItem(self.tr("Inverse Rainbow"), slicer.vtkMRMLColorTableNode().ReverseRainbow)
    selector.addItem(self.tr("Bright Red"), slicer.vtkMRMLColorTableNode().Red)
    selector.addItem(self.tr("Bright Blue"), slicer.vtkMRMLColorTableNode().Blue)
    selector.addItem(self.tr("Bright Green"), slicer.vtkMRMLColorTableNode().Green)
    selector.setCurrentIndex(0)

    return selector

  def createShiftPresetSlider(self):
    """
    Create a slider that will allow to update opacity of the rendering
    cf qSlicerVolumeRenderingPresetComboBox
    """
    shiftSlider = ctk.ctkDoubleSlider()
    shiftSlider.setValue(0.5)
    shiftSlider.singleStep = 0.1
    shiftSlider.pageStep = 0.1
    shiftSlider.maximum = 1.0
    shiftSlider.setOrientation(qt.Qt.Horizontal)
    return shiftSlider

  def createWindowLevelWidget(self):
    """
    Create a widget that will allow to modify the window and level of 2D views
    cf qMRMLWindowLevelWidget
    """
    widget = slicer.qMRMLWindowLevelWidget()
    return widget

  def createSlabThicknessSlider(self):
    """
    Create a slider that will allow to set the thickness of the MIP slab mode.
    """
    slider = qt.QSlider()
    slider.singleStep = 1
    slider.pageStep = 5
    slider.minimum = 1
    slider.maximum = 100
    slider.setOrientation(qt.Qt.Horizontal)
    slider.setValue(1)
    return slider

  def createSlabThicknessSliderReset(self, volx):
    self.slabThicknessSlider.setMaximum(volx)
  def createSlabThicknessButton2(self):
    """
    Create a slider that will allow to set the thickness of the MIP slab mode.
    """
    btn = qt.QPushButton("2")
    btn.setFixedSize(qt.QSize(20,20))
    return btn
  def createSlabThicknessButton5(self):
    """
    Create a slider that will allow to set the thickness of the MIP slab mode.
    """
    btn = qt.QPushButton("5")
    btn.setFixedSize(qt.QSize(20,20))
    return btn
  def createSlabThicknessButton10(self):
    """
    Create a slider that will allow to set the thickness of the MIP slab mode.
    """
    btn = qt.QPushButton("10")
    btn.setFixedSize(qt.QSize(20,20))
    return btn
  def createMIPThicknessCombobox(self):
    """
    Create a combobox to choose the thickness of the MIP
    """
    #---レイアウト変更--- 20221227 koyanagi
    #実際の値にあっていなかった為、修正
    selector = qt.QComboBox()
    selector.setToolTip(self.tr("Select the thickness of MIP (xx mm)"))
    selector.addItem(self.tr("0.2mm"), 0.2)
    selector.addItem(self.tr("0.5mm"), 0.5)
    selector.addItem(self.tr("1mm"), 1)
    selector.addItem(self.tr("5mm"), 5)
    selector.addItem(self.tr("10mm"), 10)
    selector.addItem(self.tr("80mm"), 80)
    selector.addItem(self.tr("100mm"), 100)
    selector.addItem(self.tr("120mm"), 120)
    selector.addItem(self.tr("140mm"), 140)
    selector.addItem(self.tr("160mm"), 160)
    selector.addItem(self.tr("180mm"), 180)
    selector.setCurrentText(self.tr("80mm"))
    #selector.setStyleSheet("""
    #    QComboBox {padding: 0px; padding-left: 4px; margin: 1px; spacing: 0; max-width: 60px; min-width: 60px;}
    #    QComboBox QAbstractItemView {border: 2px solid darkgray; selection-background-color: lightgray;}""")#レイアウト変更
    selector.setStyleSheet("""
        QComboBox {padding: 0px; padding-left: 4px; margin: 1px; spacing: 0; max-width: 9px; min-width: 9px;}
        QComboBox QAbstractItemView {border: 2px solid darkgray; selection-background-color: lightgray; max-width: 60px; min-width: 60px;}""")#レイアウト変更
    return selector

  #--- for cephalometric 20220924 koyanagi --- replacement
  def createRaycastCombobox(self):
    """
    Create a combobox to choose the thickness of the MIP
    """
    #---レイアウト変更--- 20221227 koyanagi
    selector = qt.QComboBox()
    #selector.setToolTip(self.tr("Select the Raycast mode")) #一旦日本語で対応
    selector.setToolTip(self.tr("断層画像の投影方法選択\n通常：Max"))
    selector.addItem(self.tr("Max"), 1)
    selector.addItem(self.tr("Mean"), 2)
    selector.addItem(self.tr("Min"), 3)
    selector.setCurrentText(self.tr("Max"))
    selector.setStyleSheet("""
        QComboBox {padding: 0px; padding-left: 4px; margin: 1px; spacing: 0; max-width: 60px; min-width: 60px; spacing-right: 0;}
        QComboBox QAbstractItemView {border: 2px solid darkgray; selection-background-color: lightgray;}""")#レイアウト変更
    return selector
  #-------------------------------------------

  #--- for cephalometric 20220924 koyanagi --- add
  def createFOVCombobox(self):
    # セファロ用の拡大率補正用
    """
    Create a combobox to choose the FOV for cephalometric for cephalometric magnification correction
    """
    #---レイアウト変更--- 20221227 koyanagi
    selector = qt.QComboBox()
    #selector.setToolTip(self.tr("Select the FOV")) #一旦日本語で対応
    selector.setToolTip(self.tr("セファロ用の補正値選択"))
    selector.addItem("", 0)
    for num in range(100, 400, 5): #レンジは確認後に修正
      selector.addItem(str(num), num)
    selector.setCurrentText(self.tr(""))
    selector.setStyleSheet("""
        QComboBox {padding: 0px; padding-left: 4px; margin: 1px; spacing: 0; width: 35px;}
        QComboBox QAbstractItemView {border: 2px solid darkgray; selection-background-color: lightgray;}
    	""")#レイアウト変更
    return selector
  #-------------------------------------------

  #---レイアウト変更--- 20221227 koyanagi
  #---レイアウト用　素材　------------------------------
  def _createSeparator(self):#RFVisualizationUI用のセパレーター
    separator = qt.QFrame()
    separator.setFrameShape(qt.QFrame.HLine)
    separator.setFrameShadow(qt.QFrame.Sunken)
    separator.setStyleSheet("max-height: 1px; min-height: 1px; padding: 0px; spacing: 10; background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #f0f0f0, stop:1 #f0f0f0);")#グラデーション
    return separator

  def _createLabel(self, LabelText=""):#RFVisualizationUI用のレイアウト用ラベル
    layoutLabel = qt.QLabel(LabelText)
    layoutLabel.setStyleSheet("QLabel {min-width: 50px; max-width: 50px; spacing: 0; margin: 0px;}")#固定長
    return layoutLabel
  #---------------------------------------------------

  def customMouseAction3D(self):
    threeDViewWidget = slicer.app.layoutManager().threeDWidget(0)
    cameraDisplayableManager = threeDViewWidget.threeDView().displayableManagerByClassName("vtkMRMLCameraDisplayableManager")
    cameraWidget = cameraDisplayableManager.GetCameraWidget()

    #Remove Button Action
    # Right 
    cameraWidget.SetEventTranslationClickAndDrag(cameraWidget.WidgetStateIdle, vtk.vtkCommand.RightButtonPressEvent, vtk.vtkEvent.NoModifier, cameraWidget.WidgetStateRotate, vtk.vtkWidgetEvent.NoEvent, vtk.vtkWidgetEvent.NoEvent)
    # Left
    cameraWidget.SetEventTranslationClickAndDrag(cameraWidget.WidgetStateIdle, vtk.vtkCommand.LeftButtonPressEvent, vtk.vtkEvent.NoModifier, cameraWidget.WidgetStateScale, vtk.vtkWidgetEvent.NoEvent, vtk.vtkWidgetEvent.NoEvent)
    # Middle
    cameraWidget.SetEventTranslationClickAndDrag(cameraWidget.WidgetStateIdle, vtk.vtkCommand.MiddleButtonPressEvent, vtk.vtkEvent.NoModifier, cameraWidget.WidgetStateRotate, vtk.vtkWidgetEvent.NoEvent, vtk.vtkWidgetEvent.NoEvent)
    # Mouse Wheel
    cameraWidget.SetEventTranslation(cameraWidget.WidgetStateIdle, vtk.vtkCommand.MouseWheelForwardEvent, vtk.vtkEvent.NoModifier, vtk.vtkWidgetEvent.NoEvent)
    cameraWidget.SetEventTranslation(cameraWidget.WidgetStateIdle, vtk.vtkCommand.MouseWheelBackwardEvent, vtk.vtkEvent.NoModifier, vtk.vtkWidgetEvent.NoEvent)

    # Set New Button Action
    # Left
    cameraWidget.SetEventTranslationClickAndDrag(cameraWidget.WidgetStateIdle, vtk.vtkCommand.LeftButtonPressEvent, vtk.vtkEvent.NoModifier, cameraWidget.WidgetStateTranslate, cameraWidget.WidgetEventTranslateStart, cameraWidget.WidgetEventTranslateEnd)
    # Right 
    cameraWidget.SetEventTranslationClickAndDrag(cameraWidget.WidgetStateIdle, vtk.vtkCommand.RightButtonPressEvent, vtk.vtkEvent.NoModifier, cameraWidget.WidgetStateRotate, cameraWidget.WidgetEventRotateStart, cameraWidget.WidgetEventRotateEnd)
    # Middle
    cameraWidget.SetEventTranslationClickAndDrag(cameraWidget.WidgetStateIdle, vtk.vtkCommand.MiddleButtonPressEvent, vtk.vtkEvent.NoModifier, cameraWidget.WidgetStateScale, cameraWidget.WidgetEventScaleStart, cameraWidget.WidgetEventScaleEnd)
 
  def customMouseAction2D(self):
    lm = slicer.app.layoutManager()
    for sliceViewName in lm.sliceViewNames():
      sliceViewWidget = slicer.app.layoutManager().sliceWidget(sliceViewName)
      displayableManager = sliceViewWidget.sliceView().displayableManagerByClassName("vtkMRMLCrosshairDisplayableManager")
      w = displayableManager.GetSliceIntersectionWidget()

      #Remove Button Action
      w.SetEventTranslationClickAndDrag(w.WidgetStateIdle, vtk.vtkCommand.MiddleButtonPressEvent, vtk.vtkEvent.NoModifier, w.WidgetStateZoomSlice, vtk.vtkWidgetEvent.NoEvent, vtk.vtkWidgetEvent.NoEvent)

      # Set New Button Action 
      w.SetEventTranslationClickAndDrag(w.WidgetStateIdle, vtk.vtkCommand.LeftButtonPressEvent, vtk.vtkEvent.NoModifier, w.WidgetStateMPR, w.WidgetEventMPRStart, w.WidgetEventMPREnd)
      w.SetEventTranslationClickAndDrag(w.WidgetStateIdle, vtk.vtkCommand.MiddleButtonPressEvent, vtk.vtkEvent.NoModifier, w.WidgetStateZoomSlice, w.WidgetEventZoomSliceStart, w.WidgetEventZoomSliceEnd)
