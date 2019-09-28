import numpy as np
import PIL.Image as Image
import PIL.ImageColor as ImageColor
import PIL.ImageDraw as ImageDraw
import PIL.ImageFont as ImageFont
from skimage import img_as_ubyte, exposure
#custom package for loading configs, model class and detection func
from cropmask import model_configs
from cropmask.mrcnn import model as modellib
import tensorflow as tf
import skimage.io as skio
from rasterio.plot import reshape_as_image
from rasterio.io import MemoryFile
# Core detection functions

def open_image(image_bytes):
    """ Open an image in binary format using PIL.Image and convert to RGB mode
    Args:
        image_bytes: an image in binary format read from the POST request's body

    Returns:
        an PIL image object in RGB mode
    """
    # image = Image.open(image_bytes)
    # if image.mode not in ('RGBA', 'RGB'):
    #     raise AttributeError('Input image not in RGBA or RGB mode and cannot be processed.')
    # if image.mode == 'RGBA':
    #     # Image.convert() returns a converted copy of this image
    #     image = image.convert(mode='RGB')
    # return image
    # https://docs.python.org/3/library/io.html#io.BytesIO
    with MemoryFile(image_bytes) as memfile:
        with memfile.open() as src:
            meta = src.meta
            arr = reshape_as_image(src.read())
    # returns the array for detection and the PIL img object for drawing since model trained on int16
    # and PIL can't read 3 band RGB int 16 tiff
    # so we use img_as_ubyte to conver 16 bit array to 8 bit. exposure is used to increase the color contrast
    return arr, Image.fromarray(img_as_ubyte(exposure.equalize_adapthist(arr)), mode='RGB'), meta


def generate_detections(arr):
    """ Generates a set of bounding boxes with confidence and class prediction for one input image file.

    Args:
        detection_model: a mrcnn model class object containing already loaded segmentation weights
        image_file: a PIL Image object

    Returns:
        boxes, scores, classes, and the image loaded from the input image_file - for one image
    """
        # Load the model
    # The model was copied to this location when the container was built; see ../Dockerfile
    config = model_configs.LandsatInferenceConfig(3)
    print('keras_detector.py: Loading model weights...')
    LOGS_DIR = "/app/keras_iNat_api/logs"
    with tf.device("/cpu:0"):
      model = modellib.MaskRCNN(mode="inference",
                                model_dir=LOGS_DIR,
                                config=config)
    model_path = '/home/rave/CropMask_RCNN/app/keras_iNat_api/mask_rcnn_landsat-512-cp_0042.h5'
    model.load_weights(model_path, by_name=True)
    print('keras_detector.py: Model weights loaded.')

    result = model.detect([arr], verbose=1)
    r = result[0]
    return r['rois'], r['class_ids'], r['scores'], r['masks']# these are lists of bboxes, scores etc

# Rendering functions
def render_bounding_boxes(boxes, scores, classes, image, label_map={}, confidence_threshold=0.5):
    """Renders bounding boxes, label and confidence on an image if confidence is above the threshold.

    Args:
        boxes, scores, classes:  outputs of generate_detections.
        image: PIL.Image object, output of generate_detections.
        label_map: optional, mapping the numerical label to a string name.
        confidence_threshold: threshold above which the bounding box is rendered.

    image is modified in place!

    """
    display_boxes = []
    display_strs = []  # list of list, one list of strings for each bounding box (to accommodate multiple labels)

    for box, score, clss in zip(boxes, scores, classes):
        if score > confidence_threshold:
            print('Confidence of detection greater than threshold: ', score)
            display_boxes.append(box)
            clss = int(clss)
            label = label_map[clss] if clss in label_map else str(clss)
            displayed_label = '{}: {}%'.format(label, round(100*score))
            display_strs.append([displayed_label])

    display_boxes = np.array(display_boxes)
    draw_bounding_boxes_on_image(image, display_boxes, display_str_list_list=display_strs)

# the following two functions are from https://github.com/tensorflow/models/blob/master/research/object_detection/utils/visualization_utils.py

def draw_bounding_boxes_on_image(image,
                                 boxes,
                                 color='LimeGreen',
                                 thickness=1,
                                 display_str_list_list=()):
  """Draws bounding boxes on image.

  Args:
    image: a PIL.Image object.
    boxes: a 2 dimensional numpy array of [N, 4]: (ymin, xmin, ymax, xmax).
           The coordinates are in normalized format between [0, 1].
    color: color to draw bounding box. Default is red.
    thickness: line thickness. Default value is 4.
    display_str_list_list: list of list of strings.
                           a list of strings for each bounding box.
                           The reason to pass a list of strings for a
                           bounding box is that it might contain
                           multiple labels.

  Raises:
    ValueError: if boxes is not a [N, 4] array
  """
  boxes_shape = boxes.shape
  if not boxes_shape:
    return
  if len(boxes_shape) != 2 or boxes_shape[1] != 4:
    raise ValueError('Input must be of size [N, 4]')
  for i in range(boxes_shape[0]):
    display_str_list = ()
    if display_str_list_list:
      display_str_list = display_str_list_list[i]
    draw_bounding_box_on_image(image, boxes[i, 0], boxes[i, 1], boxes[i, 2],
                               boxes[i, 3], color, thickness, display_str_list, use_normalized_coordinates=False)


def draw_bounding_box_on_image(image,
                               ymin,
                               xmin,
                               ymax,
                               xmax,
                               color='red',
                               thickness=1,
                               display_str_list=(),
                               use_normalized_coordinates=True):
  """Adds a bounding box to an image.

  Bounding box coordinates can be specified in either absolute (pixel) or
  normalized coordinates by setting the use_normalized_coordinates argument.

  Each string in display_str_list is displayed on a separate line above the
  bounding box in black text on a rectangle filled with the input 'color'.
  If the top of the bounding box extends to the edge of the image, the strings
  are displayed below the bounding box.

  Args:
    image: a PIL.Image object.
    ymin: ymin of bounding box.
    xmin: xmin of bounding box.
    ymax: ymax of bounding box.
    xmax: xmax of bounding box.
    color: color to draw bounding box. Default is red.
    thickness: line thickness. Default value is 4.
    display_str_list: list of strings to display in box
                      (each to be shown on its own line).
    use_normalized_coordinates: If True (default), treat coordinates
      ymin, xmin, ymax, xmax as relative to the image.  Otherwise treat
      coordinates as absolute.
  """
  draw = ImageDraw.Draw(image)
  im_width, im_height = image.size
  if use_normalized_coordinates:
    (left, right, top, bottom) = (xmin * im_width, xmax * im_width,
                                  ymin * im_height, ymax * im_height)
  else:
    (left, right, top, bottom) = (xmin, xmax, ymin, ymax)
  draw.line([(left, top), (left, bottom), (right, bottom),
             (right, top), (left, top)], width=thickness, fill=color)
  try:
    font = ImageFont.truetype('arial.ttf', 24)
  except IOError:
    font = ImageFont.load_default()

  # If the total height of the display strings added to the top of the bounding
  # box exceeds the top of the image, stack the strings below the bounding box
  # instead of above.
  display_str_heights = [font.getsize(ds)[1] for ds in display_str_list]
  # Each display_str has a top and bottom margin of 0.05x.
  total_display_str_height = (1 + 2 * 0.05) * sum(display_str_heights)

  if top > total_display_str_height:
    text_bottom = top
  else:
    text_bottom = bottom + total_display_str_height
  # Reverse list and print from bottom to top.
  for display_str in display_str_list[::-1]:
    text_width, text_height = font.getsize(display_str)
    margin = np.ceil(0.05 * text_height)
    draw.rectangle(
        [(left, text_bottom - text_height - 2 * margin), (left + text_width,
                                                          text_bottom)],
        fill=color)
    draw.text(
        (left + margin, text_bottom - text_height - margin),
        display_str,
        fill='black',
        font=font)
    text_bottom -= text_height - 2 * margin

def instance_preds_to_label_arr(pred_arr):
    """Convert a set of instance predictions from a neural net to a labeled mask.
    Source code slightly adapted from the solaris python package.
    Arguments
    ---------
    pred_arr : :class:`numpy.ndarray`
        A set of predictions generated by a neural net (generally in ``float``
        dtype). This can be a 2D array (no detections) or a 3D array (at 
        least one detection, in which case it will be convered to a 2D mask 
        output with optional channel scaling (see the `channel_scaling` argument). 
        If a filename is provided instead of an array, the image will be loaded 
        using scikit-image. Background class must be 0.
    Returns
    -------
    mask_arr : :class:`numpy.ndarray`
        A 2D boolean ``numpy`` array with an integer for an instance of foreground 
        pixels and `0` for background.
    """

    if len(pred_arr.shape) == 3:
        channel_scaling = np.arange(1,pred_arr.shape[-1]+1)
        pred_arr = np.sum(pred_arr*np.array(channel_scaling), axis=-1)

    mask_arr = pred_arr.astype('uint8')

    return mask_arr


def mask_to_poly_gdf(pred_arr, ref=None,
                         output_path=None, output_type='csv', min_area=0,
                         bg_threshold=0, do_transform=None, simplify=False,
                         tolerance=0.5, **kwargs):
    """Get polygons from an image mask. Source coded slightly adapted from the 
    solaris python package.
    Arguments
    ---------
    pred_arr : :class:`numpy.ndarray`
        A 2D array of integers. Multi-channel masks are not supported, and must
        be simplified before passing to this function. Can also pass an image
        file path here.
    channel_scaling : :class:`list`-like, optional
        If `pred_arr` is a 3D array, this argument defines how each channel
        will be combined to generate a binary output. channel_scaling should
        be a `list`-like of length equal to the number of channels in
        `pred_arr`. The following operation will be performed to convert the
        multi-channel prediction to a 2D output ::
            sum(pred_arr[channel]*channel_scaling[channel])
        If not provided, no scaling will be performend and channels will be
        summed.
    reference_im : str, optional
        The path to a reference geotiff to use for georeferencing the polygons
        in the mask. Required if saving to a GeoJSON (see the ``output_type``
        argument), otherwise only required if ``do_transform=True``.
    output_path : str, optional
        Path to save the output file to. If not provided, no file is saved.
    output_type : ``'csv'`` or ``'geojson'``, optional
        If ``output_path`` is provided, this argument defines what type of file
        will be generated - a CSV (``output_type='csv'``) or a geojson
        (``output_type='geojson'``).
    min_area : int, optional
        The minimum area of a polygon to retain. Filtering is done AFTER
        any coordinate transformation, and therefore will be in destination
        units.
    bg_threshold : int, optional
        The cutoff in ``mask_arr`` that denotes background (non-object).
        Defaults to ``0``.
    simplify : bool, optional
        If ``True``, will use the Douglas-Peucker algorithm to simplify edges,
        saving memory and processing time later. Defaults to ``False``.
    tolerance : float, optional
        The tolerance value to use for simplification with the Douglas-Peucker
        algorithm. Defaults to ``0.5``. Only has an effect if
        ``simplify=True``.
    Returns
    -------
    gdf : :class:`geopandas.GeoDataFrame`
        A GeoDataFrame of polygons.
    """

    mask_arr = instance_preds_to_label_arr(pred_arr)

    if do_transform and ref is None:
        raise ValueError(
            'Coordinate transformation requires a reference image.')

    if do_transform:
        transform = ref["transform"]
        crs = ref["crs"]
    else:
        transform = Affine(1, 0, 0, 0, 1, 0)  # identity transform
        crs = None

    mask = mask_arr > bg_threshold
    mask = mask.astype('uint8')

    polygon_generator = features.shapes(mask_arr,
                                        transform=transform,
                                        mask=mask)
    polygons = []
    values = []  # pixel values for the polygon in mask_arr
    for polygon, value in polygon_generator:
        p = shape(polygon).buffer(0.0)
        if p.area >= min_area:
            polygons.append(shape(polygon).buffer(0.0))
            values.append(value)

    polygon_gdf = gpd.GeoDataFrame({'geometry': polygons, 'value': values},
                                   crs=crs)
    if simplify:
        polygon_gdf['geometry'] = polygon_gdf['geometry'].apply(
            lambda x: x.simplify(tolerance=tolerance)
        )

    return polygon_gdf

