from enum import IntEnum, unique, Enum
import slicer

from RFViewerHomeLib import getViewBySingletonTag


@unique
class RFLayoutType(IntEnum):
  RFConventional = slicer.vtkMRMLLayoutNode.SlicerLayoutConventionalView
  RFDual3D = slicer.vtkMRMLLayoutNode.SlicerLayoutDual3DView
  RFTriple3D = slicer.vtkMRMLLayoutNode.SlicerLayoutTriple3DEndoscopyView
  RF3DOnly = slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView
  RFAxialOnly = slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView 
  RFDefaultLayout = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView
  RFMain3DLayout = slicer.vtkMRMLLayoutNode.SlicerLayoutConventionalWidescreenView
  RFLineProfileLayout = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpPlotView
  RFMainAxialLayout = slicer.vtkMRMLLayoutNode.SlicerLayoutUserView + 1
  RFMainCoronalLayout = RFMainAxialLayout + 1
  RFMainSagittalLayout = RFMainCoronalLayout + 1
  RFPanoramaLayout = RFMainSagittalLayout + 1
  RFTileLayout = RFPanoramaLayout+ 1

@unique
class ViewTag(Enum):
  Axial = "Red"
  Sagittal = "Yellow"
  Coronal = "Green"
  PanoramaFront = "PanoramaFront"
  PanoramaLateral = "PanoramaLateral"

  @staticmethod
  def mainViewTags():
    return [ViewTag.Axial, ViewTag.Coronal, ViewTag.Sagittal]
  @staticmethod
  def mainViewTags1():
    return [ViewTag.Coronal, ViewTag.Sagittal]
  @staticmethod
  def panoramicViewTags():
    return [ViewTag.PanoramaFront, ViewTag.PanoramaLateral]


def setNodeVisibleInMainViewsOnly(node):
  """
  Force input node display node to be visible in the Axial, Sagittal and Coronal views only

  :param node: vtkMRMLNode containing a valid display node
  """
  try:
    displayNode = node.GetDisplayNode()
    if not displayNode:
      return

    mainViewIds = [getViewBySingletonTag(tag).GetID() for tag in ViewTag.mainViewTags()]
    threeDViewIds = [threeDView.GetID() for threeDView in slicer.util.getNodesByClass("vtkMRMLViewNode")]

    displayNode.SetViewNodeIDs(mainViewIds + threeDViewIds)
  except AttributeError:
    return


def layoutSetup(layoutManager):
  """ Setup custom layouts to the layout manager
  """

  view2D = r"""
  <view class="vtkMRMLSliceNode" singletontag="{singletonTag}">
    <property name="orientation" action="default">{orientation}</property>
    <property name="viewlabel" action="default">{viewLabel}</property>
    <property name="viewcolor" action="default">{viewColor}</property>
  </view>
  """

  axialView = view2D.format(singletonTag=ViewTag.Axial.value, orientation="Axial", viewLabel="R", viewColor="#F34A33")
  sagittalView = view2D.format(singletonTag=ViewTag.Sagittal.value, orientation="Sagittal", viewLabel="Y", viewColor="#EDD54C")
  coronalView = view2D.format(singletonTag=ViewTag.Coronal.value, orientation="Coronal", viewLabel="G", viewColor="#6EB04B")

  greyColor = "#8C8C8C"
  panoramaFrontView = view2D.format(singletonTag=ViewTag.PanoramaFront.value, orientation="Coronal",
                                    viewLabel=ViewTag.PanoramaFront.value, viewColor=greyColor)
  panoramaLateralView = view2D.format(singletonTag=ViewTag.PanoramaLateral.value, orientation="Sagittal",
                                      viewLabel=ViewTag.PanoramaLateral.value, viewColor=greyColor)

  view3D = r"""
  <view class="vtkMRMLViewNode" singletontag="1">
    <property name="viewlabel" action="default">1</property>
  </view>
  """

  globalLayout = r"""
  <layout type="tab">
  <item name="MainTab">
  <layout type="horizontal" split="true" >
    <item splitSize="500">
      {mainView}
    </item>
    <item splitSize="300">
      <layout type="vertical">
        <item>
          {subViewTop}
        </item>
        <item>
          {subViewMiddle}
        </item>
        <item>
          {subViewBottom}
        </item>
      </layout>
    </item>
  </layout>

  </item>
  </layout>
  """

  panoramaLayout = r"""
  <layout type="tab">
  <item name="MainTab">
  <layout type="vertical" split="true" >
    <item splitSize="400">
      {mainView}
    </item>
    <item splitSize="400">
      <layout type="horizontal">
        <item>
          {subViewTop}
        </item>
        <item>
          {subViewMiddle}
        </item>
        <item>
          {subViewBottom}
        </item>
      </layout>
    </item>
  </layout>

  </item>
  </layout>
  """.format(mainView=panoramaFrontView, subViewTop=panoramaLateralView, subViewMiddle=axialView, subViewBottom=view3D)

  axialLayout = globalLayout.format(mainView=axialView, subViewTop=view3D, subViewMiddle=sagittalView, subViewBottom=coronalView)
  coronalLayout = globalLayout.format(mainView=coronalView, subViewTop=view3D, subViewMiddle=axialView, subViewBottom=sagittalView)
  sagittalLayout = globalLayout.format(mainView=sagittalView, subViewTop=view3D, subViewMiddle=axialView, subViewBottom=coronalView)

  layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(RFLayoutType.RFMainAxialLayout, axialLayout)
  layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(RFLayoutType.RFMainCoronalLayout, coronalLayout)
  layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(RFLayoutType.RFMainSagittalLayout, sagittalLayout)
  layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(RFLayoutType.RFPanoramaLayout, panoramaLayout)

  """create Tile layout"""
  customLayout = """
<layout type="tab">
   <item name="タイルビュー">
        <layout type=\"vertical\">
            <item>
                <layout type=\"horizontal\">
                    <item>
                        <view class=\"vtkMRMLSliceNode\" singletontag=\"Compare1\">
                            <property name=\"orientation\" action=\"default\">Axial</property>
                            <property name=\"viewlabel\" action=\"default\">R1</property>
                            <property name=\"viewcolor\" action=\"default\">#F34A33</property>
                        </view>
                    </item>
                    <item>
                        <view class=\"vtkMRMLSliceNode\" singletontag=\"Compare2\">
                            <property name=\"orientation\" action=\"default\">Axial</property>
                            <property name=\"viewlabel\" action=\"default\">R2</property>
                            <property name=\"viewcolor\" action=\"default\">#f9a99f</property>
                        </view>
                    </item>
                </layout>
            </item>
            <item>
                <layout type=\"horizontal\">
                    <item>
                        <view class=\"vtkMRMLSliceNode\" singletontag=\"Compare3\">
                            <property name=\"orientation\" action=\"default\">Axial</property>
                            <property name=\"viewlabel\" action=\"default\">R3</property>
                            <property name=\"viewcolor\" action=\"default\">#F34A33</property>
                        </view>
                    </item>
                    <item>
                        <view class=\"vtkMRMLSliceNode\" singletontag=\"Compare4\">
                            <property name=\"orientation\" action=\"default\">Axial</property>
                            <property name=\"viewlabel\" action=\"default\">R3</property>
                            <property name=\"viewcolor\" action=\"default\">#f9a99f</property>
                        </view>
                    </item>
                </layout>
            </item>
        </layout>
    </item>
    <item name="MainTab">
        <layout type=\"horizontal\">
        <item>
          <view class=\"vtkMRMLSliceNode\" singletontag=\"Red\">
          <property name=\"orientation\" action=\"default\">Axial</property>
          <property name=\"viewlabel\" action=\"default\">R</property>
          <property name=\"viewcolor\" action=\"default\">#F34A33</property>
          </view>
        </item>
        </layout>
    </item>
 
</layout>
"""
  layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(RFLayoutType.RFTileLayout, customLayout)

  """added tab to current layout
     tab付与に時間かかっている。仕様が固まったら最初からtab付与の形を検討する(C++側の変更が必要?)"""
  layouts = [
    RFLayoutType.RFConventional,
    RFLayoutType.RFDual3D,
    RFLayoutType.RFTriple3D,
    RFLayoutType.RF3DOnly,
    RFLayoutType.RFAxialOnly,
    RFLayoutType.RFDefaultLayout,
    RFLayoutType.RFMain3DLayout,
    RFLayoutType.RFLineProfileLayout]

  for l in layouts:
    layout = layoutManager.layoutLogic().GetLayoutNode().GetLayoutDescription(l)
    tabLayout = ''.join(['<layout type="tab"> <item name="MainTab">',
                        layout,
                        '</item> </layout>'])
    layoutManager.layoutLogic().GetLayoutNode().SetLayoutDescription(l, tabLayout)

def layoutBackgroundSetup(viewNode):
  viewNode.SetBackgroundColor(0.5, 0.5, 0.5)
  viewNode.SetBackgroundColor2(0.85, 0.85, 0.85)

def getMainViewNodeIDs():
  """Returns the ID of all the views that are not for Panorama"""
  return ['vtkMRMLSliceNodeRed','vtkMRMLSliceNodeYellow','vtkMRMLSliceNodeGreen','vtkMRMLViewNode1']

def showInMainViews(displayableNode):
  """ Do not show node (markup, volume, model...) in Panorama views (different coordinated system)"""
  for mainViewNodeID in getMainViewNodeIDs():
    displayableNode.GetDisplayNode().AddViewNodeID(mainViewNodeID)
