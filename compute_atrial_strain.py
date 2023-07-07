import os
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
import math
import warnings
from scipy.spatial import distance
from skimage import measure
import cv2
from collections import defaultdict
from numpy.linalg import norm
from scipy.interpolate import splprep, splev
from scipy.ndimage.morphology import binary_closing as closing
from skimage.morphology import skeletonize
from collections import Counter
from skimage.measure import label
import pandas as pd
from scipy.interpolate import interp1d
from scipy.signal import savgol_filter
from scipy.signal import resample
import numpy as np
debug = True
Nsegments_length = 15

# Enable interactive mode in matplotlib
plt.ion()
# =============================================================================
# Function
# =============================================================================


def getLargestCC(segmentation):
    nb_labels = np.unique(segmentation)[1:]
    out_image = np.zeros_like(segmentation)
    for ncc in nb_labels:
        _aux = np.squeeze(segmentation == ncc).astype(
            float)  # get myocardial labe
        if ncc == 2 and (1.0 and 2.0 in np.unique(segmentation)):
            kernel = np.ones((2, 2), np.uint8)
            _aux = cv2.dilate(_aux, kernel, iterations=2)
            cnt_myo_seg_dil = measure.find_contours(_aux, 0.8)
            cnt_myo_seg = measure.find_contours(_aux, 0.8)
            if len(cnt_myo_seg_dil) > 1 and len(cnt_myo_seg) > 1:
                _aux = dilate_LV_myo(segmentation)
        labels = label(_aux)
        assert (labels.max() != 0)  # assume at least 1 CC
        largestCC = labels == np.argmax(np.bincount(labels.flat)[1:]) + 1
        out_image += largestCC * ncc
    return out_image


def dilate_LV_myo(seg):
    # Load the image array with the three masks
    try:
        myo_seg = np.squeeze(seg == 2).astype(float)
        bp_seg = np.squeeze(seg == 1).astype(int)
        la_seg = np.squeeze(seg == 3).astype(int)
        # find the indices of the pixels in structure1 and structure2
        idx_structure1 = np.argwhere(bp_seg == 1)
        idx_structure2 = np.argwhere(la_seg == 1)
        # compute the distance between each pixel in structure1 and the closest pixel in structure2
        # using the Euclidean distance
        distances_x = distance.cdist(
            idx_structure1, idx_structure2, 'euclidean').min(axis=1)
        # Get the threshold value for the 25% furthest pixels
        threshold = np.percentile(distances_x, 75)
        # create a new array with the same shape as the original mask
        dist_map = np.zeros_like(bp_seg, dtype=float)
        dist_map[idx_structure1[:, 0], idx_structure1[:, 1]] = distances_x
        structure9 = np.zeros_like(bp_seg)

        # Set pixels that are 25% furthest away from the center of structure2 to 1
        structure9[np.where(dist_map > threshold)] = 1
        structure9 = structure9.astype(np.uint8)
        kernel = np.ones((3, 3), np.uint8)
        structure9_dil = cv2.dilate(structure9, kernel, iterations=2)
        combined_mask = cv2.bitwise_or(
            myo_seg.astype(np.uint8), structure9_dil)
        # Set pixels to zero where mask3 has value 1
        combined_mask[np.where(bp_seg == 1)] = 0
        if debug:
            plt.imshow(myo_seg)
            plt.imshow(combined_mask)
    except:
        combined_mask = seg

    return combined_mask


def binarymatrix(A):
    A_aux = np.copy(A)
    A = map(tuple, A)
    dic = Counter(A)
    for (i, j) in dic.items():
        if j > 1:
            ind = np.where(((A_aux[:, 0] == i[0]) & (A_aux[:, 1] == i[1])))[0]
            A_aux = np.delete(A_aux, ind[1:], axis=0)
    if np.linalg.norm(A_aux[:, 0] - A_aux[:, -1]) < 0.01:
        A_aux = A_aux[:-1, :]
    return A_aux


# Define a function to calculate the Euclidean distance between two points
def find_distance_x(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def get_LeftAtrial_circumference(contours, atria_edge1, atria_edge2, top_atrium, fr, study_ID):
    # coordinates of the non-linear line (example)
    indice1 = np.where((contours == (sorted(contours, key=lambda p: find_distance_x(
        p[0], p[1], atria_edge1[0], atria_edge1[1]))[0])).all(axis=1))[0][0]
    indice2 = np.where((contours == (sorted(contours, key=lambda p: find_distance_x(
        p[0], p[1], atria_edge2[0], atria_edge2[1]))[0])).all(axis=1))[0][0]
    indice3 = np.where((contours == (sorted(contours, key=lambda p: find_distance_x(
        p[0], p[1], top_atrium[0], top_atrium[1]))[0])).all(axis=1))[0][0]
    # deal with cases where contour goes on from end to start of array.
    if indice1 > indice2:
        # make sure top of atrium is in contour
        if indice1 < indice3 < indice2:
            temp = indice1
            indice2 = indice1
            indice1 = temp
        contour_atria = np.concatenate(
            (contours[indice1:, :], contours[:indice2, :]), axis=0)
    else:
        # make sure top of atrium is in contour
        if not indice1 < indice3 < indice2:
            temp = indice1
            indice2 = indice1
            indice1 = temp
        contour_atria = contours[indice1:indice2, :]

    # calculate the length of the line using the distance formula
    total_length = 0
    if debug:
        plt.figure()
        plt.plot(contours[:, 1], contours[:, 0], 'r-')
        plt.plot(contour_atria[:, 1], contour_atria[:, 0])
        plt.plot(atria_edge1[1], atria_edge1[0], 'go')
        plt.plot(atria_edge2[1], atria_edge2[0], 'bo')
        plt.plot(top_atrium[1], top_atrium[0], 'bo')
        plt.title('{0} frame {1}'.format(study_ID, fr))

    for i in range(len(contour_atria)-1):
        x1, y1 = contour_atria[i, :]
        x2, y2 = contour_atria[i+1, :]
        segment_length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        total_length += segment_length
    return total_length


def get_strain(atrial_circumferences_per_phase):
    diff_lengths = atrial_circumferences_per_phase - \
        atrial_circumferences_per_phase[0]
    strain = np.divide(diff_lengths, atrial_circumferences_per_phase[0]) * 100
    return strain


def get_right_atrial_volumes(seg, _fr, _pointsRV, logger):
    """
    This function gets the centre line (height) of the atrium and atrial dimension at 15 points along this line.
    """
    _apex_RV, _rvlv_point, _free_rv_point = _pointsRV
    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(_apex_RV[1], _apex_RV[0], 'mo')
        plt.plot(_rvlv_point[1], _rvlv_point[0], 'c*')
        plt.plot(_free_rv_point[1], _free_rv_point[0], 'y*')

    mid_valve_RV = np.mean([_rvlv_point, _free_rv_point], axis=0)
    _atria_seg = np.squeeze(seg == 5).astype(float)  # get atria label
    rv_seg = np.squeeze(seg == 3).astype(float)  # get atria label

    # Generate contours from the atria
    _contours_RA = measure.find_contours(_atria_seg, 0.8)
    _contours_RA = _contours_RA[0]

    contours_RV = measure.find_contours(rv_seg, 0.8)
    contours_RV = contours_RV[0]

    # Compute distance between mid_valve and every point in contours
    dist = distance.cdist(_contours_RA, [mid_valve_RV])
    ind_mitral_valve = dist.argmin()
    mid_valve_RA = _contours_RA[ind_mitral_valve, :]
    dist = distance.cdist(_contours_RA, [mid_valve_RA])
    ind_top_atria = dist.argmax()
    top_atria = _contours_RA[ind_top_atria, :]
    ind_base1 = distance.cdist(_contours_RA, [_rvlv_point]).argmin()
    ind_base2 = distance.cdist(_contours_RA, [_free_rv_point]).argmin()
    atria_edge1 = _contours_RA[ind_base1, :]
    atria_edge2 = _contours_RA[ind_base2, :]

    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(_contours_RA[:, 1], _contours_RA[:, 0], 'r-')
        plt.plot(contours_RV[:, 1], contours_RV[:, 0], 'k-')
        plt.plot(top_atria[1], top_atria[0], 'mo')
        plt.plot(mid_valve_RA[1], mid_valve_RA[0], 'co')
        plt.plot(atria_edge1[1], atria_edge1[0], 'go')
        plt.plot(atria_edge2[1], atria_edge2[0], 'bo')
        plt.plot(_rvlv_point[1], _rvlv_point[0], 'k*')
        plt.plot(_free_rv_point[1], _free_rv_point[0], 'b*')

    # Rotate contours by theta degrees
    radians = np.arctan2(np.array((atria_edge1[0] - atria_edge2[0]) / 2),
                         np.array((atria_edge1[1] - atria_edge2[1]) / 2))

    # Rotate contours
    _x = _contours_RA[:, 1]
    y = _contours_RA[:, 0]
    xx_B = _x * math.cos(radians) + y * math.sin(radians)
    yy_B = -_x * math.sin(radians) + y * math.cos(radians)

    # Rotate points
    x_1 = atria_edge1[1]
    y_1 = atria_edge1[0]
    x_2 = atria_edge2[1]
    y_2 = atria_edge2[0]
    x_4 = top_atria[1]
    y_4 = top_atria[0]
    x_5 = mid_valve_RA[1]
    y_5 = mid_valve_RA[0]

    xx_1 = x_1 * math.cos(radians) + y_1 * math.sin(radians)
    yy_1 = -x_1 * math.sin(radians) + y_1 * math.cos(radians)
    xx_2 = x_2 * math.cos(radians) + y_2 * math.sin(radians)
    yy_2 = -x_2 * math.sin(radians) + y_2 * math.cos(radians)
    xx_4 = x_4 * math.cos(radians) + y_4 * math.sin(radians)
    yy_4 = -x_4 * math.sin(radians) + y_4 * math.cos(radians)
    xx_5 = x_5 * math.cos(radians) + y_5 * math.sin(radians)
    yy_5 = -x_5 * math.sin(radians) + y_5 * math.cos(radians)

    # make vertical line through mid_valve_from_atriumcontours_rot
    contours_RA_rot = np.asarray([xx_B, yy_B]).T
    top_atria_rot = np.asarray([xx_4, yy_4])

    # Make more points for the contours.
    intpl_XX = []
    intpl_YY = []
    for ind, coords in enumerate(contours_RA_rot):
        coords1 = coords
        if ind < (len(contours_RA_rot) - 1):
            coords2 = contours_RA_rot[ind + 1]

        else:
            coords2 = contours_RA_rot[0]
        warnings.simplefilter('ignore', np.RankWarning)
        coeff = np.polyfit([coords1[0], coords2[0]], [
                           coords1[1], coords2[1]], 1)
        xx_es = np.linspace(coords1[0], coords2[0], 10)
        intp_val = np.polyval(coeff, xx_es)
        intpl_XX = np.hstack([intpl_XX, xx_es])
        intpl_YY = np.hstack([intpl_YY, intp_val])

    contour_smth = np.vstack([intpl_XX, intpl_YY]).T

    # find the crossing between vert_line and contours_RA_rot.
    dist2 = distance.cdist(contour_smth, [top_atria_rot])
    min_dist2 = np.min(dist2)
    # # step_closer
    newy_atra = top_atria_rot[1] + min_dist2
    new_top_atria = [top_atria_rot[0], newy_atra]
    dist3 = distance.cdist(contour_smth, [new_top_atria])
    ind_min_dist3 = dist3.argmin()

    ind_alt_atria_top = contours_RA_rot[:, 1].argmin()
    final_mid_avalve = np.asarray([xx_5, yy_5])
    final_top_atria = np.asarray(
        [contours_RA_rot[ind_alt_atria_top, 0], contours_RA_rot[ind_alt_atria_top, 1]])
    final_perp_top_atria = contour_smth[ind_min_dist3, :]
    final_atrial_edge1 = np.asarray([xx_1, yy_1])
    final_atrial_edge2 = np.asarray([xx_2, yy_2])

    if debug:
        plt.figure()
        plt.plot(contour_smth[:, 0], contour_smth[:, 1], 'r-')
        plt.plot(final_atrial_edge2[0], final_atrial_edge2[1], 'y*')
        plt.plot(final_atrial_edge1[0], final_atrial_edge1[1], 'm*')
        plt.plot(final_top_atria[0], final_top_atria[1], 'c*')
        plt.plot(final_mid_avalve[0], final_mid_avalve[1], 'b*')
        plt.title('RA 4Ch frame {}'.format(_fr))

    alength_top = distance.pdist([final_mid_avalve, final_top_atria])[0]
    alength_perp = distance.pdist([final_mid_avalve, final_perp_top_atria])[0]
    a_segmts = (final_mid_avalve[1] - final_top_atria[1]) / Nsegments_length

    # get length dimension (width) of atrial seg at each place.
    a_diams = np.zeros(Nsegments_length)
    diam1 = abs(np.diff([xx_1, xx_2]))
    points_aux = np.zeros(((Nsegments_length - 1) * 2, 2))
    k = 0
    for ib in range(Nsegments_length):
        if ib == 0:
            a_diams[ib] = diam1
        else:
            vert_y = final_mid_avalve[1] - a_segmts * ib
            rgne_vertY = a_segmts / 6
            min_Y = vert_y - rgne_vertY
            max_Y = vert_y + rgne_vertY
            ind_sel_conts = np.where(np.logical_and(
                intpl_YY >= min_Y, intpl_YY <= max_Y))[0]

            if len(ind_sel_conts) == 0:
                logger.error('Problem in disk {}'.format(ib))
                continue

            y_sel_conts = contour_smth[ind_sel_conts, 1]
            x_sel_conts = contour_smth[ind_sel_conts, 0]
            min_ys = np.argmin(np.abs(y_sel_conts - vert_y))

            p1 = ind_sel_conts[min_ys]
            point1 = contour_smth[p1]

            mean_x = np.mean([np.min(x_sel_conts), np.max(x_sel_conts)])
            if mean_x < point1[0]:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] < mean_x)[0]
                pts = contour_smth[ind_sel_conts[ind_xs], :]
                min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                point2 = pts[min_ys]
                a_diam = distance.pdist([point1, point2])[0]
            elif np.min(x_sel_conts) == np.max(x_sel_conts):
                logger.info(
                    'Frame {}, disk {} diameter is zero'.format(_fr, ib))
                a_diam = 0
                point2 = np.zeros(2)
                point1 = np.zeros(2)
            else:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] > mean_x)[0]
                if len(ind_xs) > 0:
                    pts = contour_smth[ind_sel_conts[ind_xs], :]
                    min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                    point2 = pts[min_ys]
                    a_diam = distance.pdist([point1, point2])[0]
                else:
                    a_diam = 0
                    point2 = np.zeros(2)
                    point1 = np.zeros(2)
                    logger.info(
                        'la_4Ch: Frame {}, disk {} diameter is zero'.format(_fr, ib))

            a_diams[ib] = a_diam
            points_aux[k, :] = point1
            points_aux[k + 1, :] = point2

            k += 2

    points_rotate = np.zeros(((Nsegments_length - 1) * 2 + 5, 2))
    points_rotate[0, :] = final_mid_avalve
    points_rotate[1, :] = final_top_atria
    points_rotate[2, :] = final_perp_top_atria
    points_rotate[3, :] = final_atrial_edge1
    points_rotate[4, :] = final_atrial_edge2
    points_rotate[5:, :] = points_aux

    radians2 = 2 * np.pi - radians
    points_non_rotate_ = np.zeros_like(points_rotate)
    for _jj, p in enumerate(points_non_rotate_):
        points_non_rotate_[_jj, 0] = points_rotate[_jj, 0] * math.cos(radians2) + points_rotate[_jj, 1] * math.sin(
            radians2)
        points_non_rotate_[_jj, 1] = -points_rotate[_jj, 0] * math.sin(radians2) + points_rotate[_jj, 1] * math.cos(
            radians2)

    length_apex = distance.pdist([_apex_RV, _free_rv_point])
    if debug:
        plt.close('all')
    return a_diams, alength_top, alength_perp, points_non_rotate_, _contours_RA, length_apex


def get_left_atrial_volumes(seg, _seq, _fr, _points, logger):
    log_dir = '/motion_repository/UKBiobank/AICMRQC_analysis/log'
    """
    This function gets the centre line (height) of the atrium and atrial dimension at 15 points along this line.
    """
    _apex, _mid_valve, anterior_2Ch, inferior_2Ch = _points
    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(_apex[1], _apex[0], 'mo')
        plt.plot(_mid_valve[1], _mid_valve[0], 'c*')
        plt.plot(anterior_2Ch[1], anterior_2Ch[0], 'y*')
        plt.plot(inferior_2Ch[1], inferior_2Ch[0], 'r*')
        plt.savefig(os.path.join(log_dir, f'{_seq}_LV_points.png'))

    if _seq == 'la_2Ch':
        _atria_seg = np.squeeze(seg == 3).astype(float)  # get atria label
    else:
        _atria_seg = np.squeeze(seg == 4).astype(float)  # get atria label

    # Generate contours from the atria
    contours = measure.find_contours(_atria_seg, 0.8)
    contours = contours[0]

    # Compute distance between mid_valve and every point in contours
    dist = distance.cdist(contours, [_mid_valve])
    ind_mitral_valve = dist.argmin()
    _mid_valve = contours[ind_mitral_valve, :]
    dist = distance.cdist(contours, [contours[ind_mitral_valve, :]])
    ind_top_atria = dist.argmax()
    top_atria = contours[ind_top_atria, :]
    length_apex_mid_valve = distance.pdist([_apex, _mid_valve])
    length_apex_inferior_2Ch = distance.pdist([_apex, inferior_2Ch])
    length_apex_anterior_2Ch = distance.pdist([_apex, anterior_2Ch])
    lines_LV_ = np.concatenate(
        [length_apex_mid_valve, length_apex_inferior_2Ch, length_apex_anterior_2Ch])
    points_LV_ = np.vstack([_apex, _mid_valve, inferior_2Ch, anterior_2Ch])

    ind_base1 = distance.cdist(contours, [inferior_2Ch]).argmin()
    ind_base2 = distance.cdist(contours, [anterior_2Ch]).argmin()
    atria_edge1 = contours[ind_base1, :]
    atria_edge2 = contours[ind_base2, :]
    # mid valve based on atria
    x_mid_valve_atria = atria_edge1[0] + \
        ((atria_edge2[0] - atria_edge1[0]) / 2)
    y_mid_valve_atria = atria_edge1[1] + \
        ((atria_edge2[1] - atria_edge1[1]) / 2)
    mid_valve_atria = np.array([x_mid_valve_atria, y_mid_valve_atria])
    ind_mid_valve = distance.cdist(contours, [mid_valve_atria]).argmin()
    mid_valve_atria = contours[ind_mid_valve, :]

    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(top_atria[1], top_atria[0], 'mo')
        plt.plot(mid_valve_atria[1], mid_valve_atria[0], 'c*')
        plt.plot(atria_edge1[1], atria_edge1[0], 'y*')
        plt.plot(atria_edge2[1], atria_edge2[0], 'r*')
        plt.savefig(os.path.join(log_dir, f'{_seq}_atria_points.png'))

    # Rotate contours by theta degrees
    radians = np.arctan2(np.array((atria_edge2[0] - atria_edge1[0]) / 2),
                         np.array((atria_edge2[1] - atria_edge1[1]) / 2))

    # Rotate contours
    _x = contours[:, 1]
    y = contours[:, 0]
    xx_B = _x * math.cos(radians) + y * math.sin(radians)
    yy_B = -_x * math.sin(radians) + y * math.cos(radians)

    # Rotate points
    x_1 = atria_edge1[1]
    y_1 = atria_edge1[0]
    x_2 = atria_edge2[1]
    y_2 = atria_edge2[0]
    x_4 = top_atria[1]
    y_4 = top_atria[0]
    x_5 = mid_valve_atria[1]
    y_5 = mid_valve_atria[0]

    xx_1 = x_1 * math.cos(radians) + y_1 * math.sin(radians)
    yy_1 = -x_1 * math.sin(radians) + y_1 * math.cos(radians)
    xx_2 = x_2 * math.cos(radians) + y_2 * math.sin(radians)
    yy_2 = -x_2 * math.sin(radians) + y_2 * math.cos(radians)
    xx_4 = x_4 * math.cos(radians) + y_4 * math.sin(radians)
    yy_4 = -x_4 * math.sin(radians) + y_4 * math.cos(radians)
    xx_5 = x_5 * math.cos(radians) + y_5 * math.sin(radians)
    yy_5 = -x_5 * math.sin(radians) + y_5 * math.cos(radians)

    # make vertical line through mid_valve_from_atrium
    contours_rot = np.asarray([xx_B, yy_B]).T
    top_atria_rot = np.asarray([xx_4, yy_4])

    # Make more points for the contours.
    intpl_XX = []
    intpl_YY = []
    for ind, coords in enumerate(contours_rot):
        coords1 = coords
        if ind < (len(contours_rot) - 1):
            coords2 = contours_rot[ind + 1]
        else:
            coords2 = contours_rot[0]
        warnings.simplefilter('ignore', np.RankWarning)
        coeff = np.polyfit([coords1[0], coords2[0]], [
                           coords1[1], coords2[1]], 1)
        xx_es = np.linspace(coords1[0], coords2[0], 10)
        intp_val = np.polyval(coeff, xx_es)
        intpl_XX = np.hstack([intpl_XX, xx_es])
        intpl_YY = np.hstack([intpl_YY, intp_val])

    contour_smth = np.vstack([intpl_XX, intpl_YY]).T

    # find the crossing between vert_line and contours_rot.
    dist2 = distance.cdist(contour_smth, [top_atria_rot])
    min_dist2 = np.min(dist2)
    newy_atra = top_atria_rot[1] + min_dist2
    new_top_atria = [top_atria_rot[0], newy_atra]
    dist3 = distance.cdist(contour_smth, [new_top_atria])
    ind_min_dist3 = dist3.argmin()

    ind_alt_atria_top = contours_rot[:, 1].argmin()
    final_top_atria = np.asarray(
        [contours_rot[ind_alt_atria_top, 0], contours_rot[ind_alt_atria_top, 1]])
    final_perp_top_atria = contour_smth[ind_min_dist3, :]
    final_atrial_edge1 = np.asarray([xx_1, yy_1])
    final_atrial_edge2 = np.asarray([xx_2, yy_2])
    final_mid_avalve = np.asarray([xx_5, yy_5])

    if debug:
        plt.figure()
        plt.plot(contour_smth[:, 0], contour_smth[:, 1], 'r-')
        plt.plot(final_atrial_edge2[0], final_atrial_edge2[1], 'y*')
        plt.plot(final_atrial_edge1[0], final_atrial_edge1[1], 'm*')
        plt.plot(final_perp_top_atria[0], final_perp_top_atria[1], 'ko')
        plt.plot(final_top_atria[0], final_top_atria[1], 'c*')
        plt.plot(new_top_atria[0], new_top_atria[1], 'g*')
        plt.plot(final_mid_avalve[0], final_mid_avalve[1], 'b*')
        plt.title('LA {}  frame {}'.format(_seq, _fr))
        plt.savefig(os.path.join(log_dir, f'{_seq}_atria_points2.png'))

    # now find length of atrium divide in the  15 segments
    alength_top = distance.pdist([final_mid_avalve, final_top_atria])[0]
    alength_perp = distance.pdist([final_mid_avalve, final_perp_top_atria])[0]
    a_segmts = (final_mid_avalve[1] - final_top_atria[1]) / Nsegments_length

    a_diams = np.zeros(Nsegments_length)
    diam1 = abs(np.diff([xx_1, xx_2]))
    points_aux = np.zeros(((Nsegments_length - 1) * 2, 2))
    k = 0
    for ib in range(Nsegments_length):
        if ib == 0:
            a_diams[ib] = diam1
        else:
            vert_y = final_mid_avalve[1] - a_segmts * ib
            rgne_vertY = a_segmts / 6
            min_Y = vert_y - rgne_vertY
            max_Y = vert_y + rgne_vertY
            ind_sel_conts = np.where(np.logical_and(
                intpl_YY >= min_Y, intpl_YY <= max_Y))[0]

            if len(ind_sel_conts) == 0:
                logger.info('Problem in disk {}'.format(ib))
                continue

            y_sel_conts = contour_smth[ind_sel_conts, 1]
            x_sel_conts = contour_smth[ind_sel_conts, 0]
            min_ys = np.argmin(np.abs(y_sel_conts - vert_y))

            p1 = ind_sel_conts[min_ys]
            point1 = contour_smth[p1]

            mean_x = np.mean([np.min(x_sel_conts), np.max(x_sel_conts)])
            if mean_x < point1[0]:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] < mean_x)[0]
                pts = contour_smth[ind_sel_conts[ind_xs], :]
                min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                point2 = pts[min_ys]
                a_diam = distance.pdist([point1, point2])[0]

            elif np.min(x_sel_conts) == np.max(x_sel_conts):
                logger.info(
                    'Frame {}, disk {} diameter is zero'.format(_fr, ib))
                a_diam = 0
                point2 = np.zeros(2)
                point1 = np.zeros(2)
            else:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] > mean_x)[0]
                if len(ind_xs) > 0:
                    pts = contour_smth[ind_sel_conts[ind_xs], :]
                    min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                    point2 = pts[min_ys]
                    a_diam = distance.pdist([point1, point2])[0]

                else:
                    a_diam = 0
                    point2 = np.zeros(2)
                    point1 = np.zeros(2)
                    logger.info(
                        'la_4Ch - Frame {}, disk {} diameter is zero'.format(_fr, ib))

            a_diams[ib] = a_diam
            points_aux[k, :] = point1
            points_aux[k + 1, :] = point2

            k += 2

    points_rotate = np.zeros(((Nsegments_length - 1) * 2 + 5, 2))
    points_rotate[0, :] = final_mid_avalve
    points_rotate[1, :] = final_top_atria
    points_rotate[2, :] = final_perp_top_atria
    points_rotate[3, :] = final_atrial_edge1
    points_rotate[4, :] = final_atrial_edge2
    points_rotate[5:, :] = points_aux

    radians2 = 2 * np.pi - radians
    points_non_rotate_ = np.zeros_like(points_rotate)
    for _jj, p in enumerate(points_non_rotate_):
        points_non_rotate_[_jj, 0] = points_rotate[_jj, 0] * math.cos(radians2) + points_rotate[_jj, 1] * math.sin(
            radians2)
        points_non_rotate_[_jj, 1] = -points_rotate[_jj, 0] * math.sin(radians2) + points_rotate[_jj, 1] * math.cos(
            radians2)
    if debug:
        plt.close('all')
    return a_diams, alength_top, alength_perp, points_non_rotate_, contours, lines_LV_, points_LV_


def detect_LV_points(seg, logger):
    myo_seg = np.squeeze(seg == 2).astype(float)
    kernel = np.ones((2, 2), np.uint8)
    # check if disconnected LV and use bloodpool to fill
    cnt_myo_seg = measure.find_contours(myo_seg, 0.8)
    if len(cnt_myo_seg) > 1:
        myo_seg = dilate_LV_myo(seg)
    myo2 = get_processed_myocardium(myo_seg, _label=1)
    cl_pts, _mid_valve = get_sorted_sk_pts(myo2, logger)
    dist_myo = distance.cdist(cl_pts, [_mid_valve])
    ind_apex = dist_myo.argmax()
    _apex = cl_pts[ind_apex, :]
    _septal_mv = cl_pts[0, 0], cl_pts[0, 1]
    _ant_mv = cl_pts[-1, 0], cl_pts[-1, 1]

    return np.asarray(_apex), np.asarray(_mid_valve), np.asarray(_septal_mv), np.asarray(_ant_mv)


def get_processed_myocardium(seg, _label=2):
    """
    This function tidies the LV myocardial segmentation, taking only the single
    largest connected component, and performing an opening (erosion+dilation)
    """

    myo_aux = np.squeeze(seg == _label).astype(float)  # get myocardial label
    myo_aux = closing(myo_aux, structure=np.ones((2, 2))).astype(float)
    cc_aux = measure.label(myo_aux, connectivity=1)
    ncc_aux = len(np.unique(cc_aux))

    if not ncc_aux <= 1:
        cc_counts, cc_inds = np.histogram(cc_aux, range(ncc_aux + 1))
        cc_inds = cc_inds[:-1]
        cc_inds_sorted = [_x for (y, _x) in sorted(zip(cc_counts, cc_inds))]
        # Take second largest CC (after background)
        biggest_cc_ind = cc_inds_sorted[-2]
        myo_aux = closing(myo_aux, structure=np.ones((2, 2))).astype(float)

        # Take largest connected component
        if not (len(np.where(cc_aux > 0)[0]) == len(np.where(cc_aux == biggest_cc_ind)[0])):
            mask = cc_aux == biggest_cc_ind
            myo_aux *= mask
            myo_aux = closing(myo_aux).astype(float)

    return myo_aux


def get_sorted_sk_pts(myo, logger, n_samples=48, centroid=np.array([0, 0])):
    #   ref -       reference start point for spline point ordering
    #   n_samples  output number of points for sampling spline

    # check for side branches? need connectivity check
    sk_im = skeletonize(myo)

    myo_pts = np.asarray(np.nonzero(myo)).transpose()
    sk_pts = np.asarray(np.nonzero(sk_im)).transpose()

    # convert to radial coordinates and sort circumferential
    if centroid[0] == 0 and centroid[1] == 0:
        centroid = np.mean(sk_pts, axis=0)

    # get skeleton consisting only of longest path
    sk_im = get_longest_path(sk_im, logger)

    # sort centreline points based from boundary points at valves as start
    # and end point. Make ref point out of LV through valve
    out = skeleton_endpoints(sk_im.astype(int))
    end_pts = np.asarray(np.nonzero(out)).transpose()
    sk_pts = np.asarray(np.nonzero(sk_im)).transpose()

    if len(end_pts) > 2:
        logger.info('Error! More than 2 end-points in LA myocardial skeleton.')
        cl_pts = []
        _mid_valve = []
        return cl_pts, _mid_valve
    else:
        # set reference to vector pointing from centroid to mid-valve
        _mid_valve = np.mean(end_pts, axis=0)
        ref = (_mid_valve - centroid) / norm(_mid_valve - centroid)
        sk_pts2 = sk_pts - centroid  # centre around centroid
        myo_pts2 = myo_pts - centroid
        theta = np.zeros([len(sk_pts2), ])
        theta_myo = np.zeros([len(myo_pts2), ])

        eps = 0.0001
        if len(sk_pts2) <= 5:
            logger.info(
                'Skeleton failed! Only of length {}'.format(len(sk_pts2)))
            cl_pts = []
            _mid_valve = []
            return cl_pts, _mid_valve
        else:
            # compute angle theta for skeleton points
            for k, ss in enumerate(sk_pts2):
                if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                    theta[k] = 0
                elif (np.dot(ref, ss) / norm(ss) < -1.0 + eps) and (np.dot(ref, ss) / norm(ss) > -1.0 - eps):
                    theta[k] = 180
                else:
                    theta[k] = math.acos(
                        np.dot(ref, ss) / norm(ss)) * 180 / np.pi
                detp = ref[0] * ss[1] - ref[1] * ss[0]
                if detp > 0:
                    theta[k] = 360 - theta[k]
            thinds = theta.argsort()
            sk_pts = sk_pts[thinds, :].astype(
                float)  # ordered centreline points

            # # compute angle theta for myo points
            for k, ss in enumerate(myo_pts2):
                # compute angle theta
                eps = 0.0001
                if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                    theta_myo[k] = 0
                elif (np.dot(ref, ss) / norm(ss) < -1.0 + eps) and (np.dot(ref, ss) / norm(ss) > -1.0 - eps):
                    theta_myo[k] = 180
                else:
                    theta_myo[k] = math.acos(
                        np.dot(ref, ss) / norm(ss)) * 180 / np.pi
                detp = ref[0] * ss[1] - ref[1] * ss[0]
                if detp > 0:
                    theta_myo[k] = 360 - theta_myo[k]
            # sub-sample and order myo points circumferential
            theta_myo.sort()

            # Remove duplicates
            sk_pts = binarymatrix(sk_pts)
            # fit b-spline curve to skeleton, sample fixed number of points
            tck, u = splprep(sk_pts.T, s=10.0, nest=-1, quiet=2)
            u_new = np.linspace(u.min(), u.max(), n_samples)
            cl_pts = np.zeros([n_samples, 2])
            cl_pts[:, 0], cl_pts[:, 1] = splev(u_new, tck)

            # get centreline theta
            cl_theta = np.zeros([len(cl_pts), ])
            cl_pts2 = cl_pts - centroid  # centre around centroid
            for k, ss in enumerate(cl_pts2):
                # compute angle theta
                if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                    cl_theta[k] = 0
                else:
                    cl_theta[k] = math.acos(
                        np.dot(ref, ss) / norm(ss)) * 180 / np.pi
                detp = ref[0] * ss[1] - ref[1] * ss[0]
                if detp > 0:
                    cl_theta[k] = 360 - cl_theta[k]
            cl_theta.sort()
            return cl_pts, _mid_valve


def get_longest_path(skel, logger):
    # first create edges from skeleton
    sk_im = skel.copy()
    # remove bad (L-shaped) junctions
    sk_im = remove_bad_junctions(sk_im, logger)

    # get seeds for longest path from existing end-points
    out = skeleton_endpoints(sk_im.astype(int))
    end_pts = np.asarray(np.nonzero(out)).transpose()
    if len(end_pts) == 0:
        logger.info('ERROR! No end-points detected! Exiting.')
    # break
    elif len(end_pts) == 1:
        logger.info('Warning! Only 1 end-point detected!')
    elif len(end_pts) > 2:
        logger.info('Warning! {} end-points detected!'.format(len(end_pts)))

    sk_pts = np.asarray(np.nonzero(sk_im)).transpose()
    # search indices of sk_pts for end points
    tmp_inds = np.ravel_multi_index(
        sk_pts.T, (np.max(sk_pts[:, 0]) + 1, np.max(sk_pts[:, 1]) + 1))
    seed_inds = np.zeros((len(end_pts), 1))
    for i, e in enumerate(end_pts):
        seed_inds[i] = int(
            np.where(tmp_inds == np.ravel_multi_index(e.T, (np.max(sk_pts[:, 0]) + 1, np.max(sk_pts[:, 1]) + 1)))[0])
    sk_im_inds = np.zeros_like(sk_im, dtype=int)

    for i, p in enumerate(sk_pts):
        sk_im_inds[p[0], p[1]] = i

    kernel1 = np.uint8([[1, 1, 1],
                        [1, 0, 1],
                        [1, 1, 1]])
    edges = []
    for i, p in enumerate(sk_pts):
        mask = sk_im_inds[p[0] - 1:p[0] + 2, p[1] - 1:p[1] + 2]
        o = np.multiply(kernel1, mask)
        for c in o[o > 0]:
            edges.append(['{}'.format(i), '{}'.format(c)])
    # create graph
    G = defaultdict(list)
    for (ss, t) in edges:
        if t not in G[ss]:
            G[ss].append(t)
        if ss not in G[t]:
            G[t].append(ss)
    # find max path
    max_path = []
    for j in range(len(seed_inds)):
        all_paths = depth_first_search(G, str(int(seed_inds[j][0])))
        max_path2 = max(all_paths, key=lambda l: len(l))
        if len(max_path2) > len(max_path):
            max_path = max_path2
    # create new image only with max path
    sk_im_maxp = np.zeros_like(sk_im, dtype=int)
    for j in max_path:
        p = sk_pts[int(j)]
        sk_im_maxp[p[0], p[1]] = 1
    return sk_im_maxp


def skeleton_endpoints(skel):
    # make out input nice, possibly necessary
    skel = skel.copy()
    skel[skel != 0] = 1
    skel = np.uint8(skel)

    # apply the convolution
    kernel = np.uint8([[1, 1, 1],
                       [1, 10, 1],
                       [1, 1, 1]])
    src_depth = -1
    filtered = cv2.filter2D(skel, src_depth, kernel)

    # now look through to find the value of 11
    out = np.zeros_like(skel)
    out[np.where(filtered == 11)] = 1

    return out


def closest_node(node, nodes):
    closest_index = distance.cdist([node], nodes).argmin()
    return nodes[closest_index]


def detect_RV_points(_seg, septal_mv, logger):
    rv_seg = np.squeeze(_seg == 3).astype(float)

    sk_pts = measure.find_contours(rv_seg, 0.8)
    if len(sk_pts) > 1:
        nb_pts = []
        for ll in range(len(sk_pts)):
            nb_pts.append(len(sk_pts[ll]))
        sk_pts = sk_pts[np.argmax(nb_pts)]
    sk_pts = np.squeeze(sk_pts)
    sk_pts = np.unique(sk_pts, axis=0)
    centroid = np.mean(sk_pts, axis=0)

    _lv_valve = closest_node(np.squeeze(septal_mv), sk_pts)
    ref = (_lv_valve - centroid) / norm(_lv_valve - centroid)

    sk_pts2 = sk_pts - centroid  # centre around centroid
    theta = np.zeros([len(sk_pts2), ])

    eps = 0.0001
    if len(sk_pts2) <= 5:
        logger.info('Skeleton failed! Only of length {}'.format(len(sk_pts2)))
        _cl_pts = []
    else:
        # compute angle theta for skeleton points
        for k, ss in enumerate(sk_pts2):
            if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                theta[k] = 0
            elif (np.dot(ref, ss) / norm(ss) < -1.0 + eps) and (np.dot(ref, ss) / norm(ss) > -1.0 - eps):
                theta[k] = 180
            else:
                theta[k] = math.acos(np.dot(ref, ss) / norm(ss)) * 180 / np.pi
            detp = ref[0] * ss[1] - ref[1] * ss[0]
            if detp > 0:
                theta[k] = 360 - theta[k]
        thinds = theta.argsort()
        sk_pts = sk_pts[thinds, :].astype(float)  # ordered centreline points

        # Remove duplicates
        sk_pts = binarymatrix(sk_pts)
        # fit b-spline curve to skeleton, sample fixed number of points
        tck, u = splprep(sk_pts.T, s=10.0, per=1, quiet=2)

        u_new = np.linspace(u.min(), u.max(), 80)
        _cl_pts = np.zeros([80, 2])
        _cl_pts[:, 0], _cl_pts[:, 1] = splev(u_new, tck)

    dist_rv = distance.cdist(_cl_pts, [_lv_valve])
    _ind_apex = dist_rv.argmax()
    _apex_RV = _cl_pts[_ind_apex, :]

    m = np.diff(_cl_pts[:, 0]) / np.diff(_cl_pts[:, 1])
    angle = np.arctan(m) * 180 / np.pi
    idx = np.sign(angle)
    _ind_free_wall = np.where(idx == -1)[0]

    _area = 10000 * np.ones(len(_ind_free_wall))
    for ai, ind in enumerate(_ind_free_wall):
        AB = np.linalg.norm(_lv_valve - _apex_RV)
        BC = np.linalg.norm(_lv_valve - _cl_pts[ind, :])
        AC = np.linalg.norm(_cl_pts[ind, :] - _apex_RV)
        if AC > 10 and BC > 10:
            _area[ai] = np.abs(AB ** 2 + BC ** 2 - AC ** 2)
    _free_rv_point = _cl_pts[_ind_free_wall[_area.argmin()], :]

    return np.asarray(_apex_RV), np.asarray(_lv_valve), np.asarray(_free_rv_point)


def remove_bad_junctions(skel, logger):
    # make out input nice, possibly necessary
    skel = skel.copy()
    skel[skel != 0] = 1
    skel = np.uint8(skel)

    # kernel_A used for unnecessary nodes in L-shaped junctions (retain diags)
    kernels_A = [np.uint8([[0, 1, 0],
                           [1, 10, 1],
                           [0, 1, 0]])]
    src_depth = -1
    for k in kernels_A:
        filtered = cv2.filter2D(skel, src_depth, k)
        skel[filtered >= 13] = 0
        if len(np.where(filtered == 14)[0]) > 0:
            logger.info('Warning! You have a 3x3 loop!')

    return skel


def depth_first_search(G, v, seen=None, path=None):
    if seen is None:
        seen = []
    if path is None:
        path = [v]

    seen.append(v)

    paths = []
    for t in G[v]:
        if t not in seen:
            t_path = path + [t]
            paths.append(tuple(t_path))
            paths.extend(depth_first_search(G, t, seen, t_path))
    return paths


def compute_atria_params(study_ID, subject_dir, results_dir, logger):
    window_size, poly_order = 7, 3
    QC_atria_2Ch, QC_atria_4Ch_LA, QC_atria_4Ch_RA = 0, 0, 0

    # =========================================================================
    # la_2Ch - calculate area and points
    # =========================================================================
    filename_la_seg_2Ch = os.path.join(subject_dir, 'la_2Ch_seg_nnUnet.nii.gz')
    if os.path.exists(filename_la_seg_2Ch):
        nim = nib.load(filename_la_seg_2Ch)
        la_seg_2Ch = nim.get_fdata()
        dx, dy, dz = nim.header['pixdim'][1:4]
        area_per_voxel = dx * dy
        if len(la_seg_2Ch.shape) == 4:
            la_seg_2Ch = la_seg_2Ch[:, :, 0, :]
        X, Y, N_frames_2Ch = la_seg_2Ch.shape

        # Get largest connected components
        for fr in range(N_frames_2Ch):
            la_seg_2Ch[:, :, fr] = getLargestCC(la_seg_2Ch[:, :, fr])

        # Compute 2ch area using number of pixels
        area_LA_2Ch = np.zeros(N_frames_2Ch)
        for fr in range(N_frames_2Ch):
            area_LA_2Ch[fr] = np.sum(
                np.squeeze(
                    la_seg_2Ch[:, :, fr] == 3).astype(float)) * area_per_voxel

        # Compute 2ch params needed for simpson's rule
        save_2ch_dict_flag = False  # Whether to save 2ch dict and points
        dict_2ch_file = os.path.join(  # dict of length values
            results_dir, f'{study_ID}_2ch_length_dict.npy')
        if os.path.exists(dict_2ch_file):
            # If already saved, load the dictionary
            logger.info('Loading pre-saved dictionary of params')
            dict_2ch = np.load(dict_2ch_file, allow_pickle=True).item()
            la_diams_2Ch = dict_2ch['la_diams_2Ch']
            length_top_2Ch = dict_2ch['length_top_2Ch']
            LA_circumf_2Ch = dict_2ch['LA_circumf_2Ch']
        else:
            # Otherwise, calculate and save points
            logger.info('Calculating points')
            save_2ch_dict_flag = True
            points_LV_2Ch = np.zeros((N_frames_2Ch, 4, 2))
            LV_atria_points_2Ch = np.zeros((N_frames_2Ch, 9, 2))
            la_diams_2Ch = np.zeros((N_frames_2Ch, Nsegments_length))
            length_top_2Ch = np.zeros(N_frames_2Ch)
            LA_circumf_cycle_2Ch = np.zeros(N_frames_2Ch)

            for fr in range(N_frames_2Ch):
                try:
                    apex, mid_valve, anterior, inferior = detect_LV_points(
                        la_seg_2Ch[:, :, fr], logger)
                    points = np.vstack([apex, mid_valve, anterior, inferior])
                    points_LV_2Ch[fr, :] = points
                except Exception:
                    logger.error(
                        'Problem detecting LV points {study_ID}'
                        ' in la_2Ch fr {fr}')
                    QC_atria_2Ch = 1

                if QC_atria_2Ch == 0:
                    try:
                        la_dia, lentop, lenperp, points_non_rotate, contours_LA, lines_LV, points_LV = \
                            get_left_atrial_volumes(
                                la_seg_2Ch[:, :, fr], 'la_2Ch', fr, points, logger)
                        la_diams_2Ch[fr, :] = la_dia * dx
                        length_top_2Ch[fr] = lentop * dx
                        # final_mid_avalve
                        LV_atria_points_2Ch[fr, 0, :] = points_non_rotate[0, :]
                        # final_top_atria
                        LV_atria_points_2Ch[fr, 1, :] = points_non_rotate[1, :]
                        # final_perp_top_atria
                        LV_atria_points_2Ch[fr, 2, :] = points_non_rotate[2, :]
                        # final_atrial_edge1
                        LV_atria_points_2Ch[fr, 3, :] = points_non_rotate[3, :]
                        # final_atrial_edge2
                        LV_atria_points_2Ch[fr, 4, :] = points_non_rotate[4, :]
                        LV_atria_points_2Ch[fr, 5, :] = points_LV[0, :]  # apex
                        # mid_valve
                        LV_atria_points_2Ch[fr, 6, :] = points_LV[1, :]
                        # inferior_2Ch
                        LV_atria_points_2Ch[fr, 7, :] = points_LV[2, :]
                        # anterior_2Ch
                        LV_atria_points_2Ch[fr, 8, :] = points_LV[3, :]
                        logger.info('Finished calculating points')

                        # compute atrial circumference
                        LA_circumf_2Ch = get_LeftAtrial_circumference(contours_LA, [points_non_rotate[3, 1], points_non_rotate[3, 0]], [
                            points_non_rotate[4, 1], points_non_rotate[4, 0]], [points_non_rotate[1, 1], points_non_rotate[1, 0]], fr, study_ID)
                        LA_circumf_len_2Ch = LA_circumf_2Ch * dx
                        LA_circumf_cycle_2Ch[fr] = LA_circumf_len_2Ch
                    except Exception:
                        logger.error('Problem in disk-making with subject {} in la_2Ch fr {}'.
                                     format(study_ID, fr))
                        QC_atria_2Ch = 1

        # =====================================================================
        # Compute 2ch strain
        # =====================================================================
        if QC_atria_2Ch == 0:
            LA_strain_circum_2Ch = get_strain(LA_circumf_cycle_2Ch)
            LA_strain_longitud_2ch = get_strain(length_top_2Ch)
            np.savetxt(os.path.join(
                results_dir, 'LA_strain_circum_2Ch.txt'), LA_strain_circum_2Ch)
            np.savetxt(os.path.join(
                results_dir, 'LA_strain_longitud_2Ch.txt'), LA_strain_longitud_2ch)

            x = np.linspace(0, N_frames_2Ch - 1, N_frames_2Ch)
            xx = np.linspace(np.min(x), np.max(x), N_frames_2Ch)
            itp = interp1d(x, LA_strain_circum_2Ch)
            yy_sg = savgol_filter(itp(xx), window_size, poly_order)
            LA_strain_circum_2Ch_smooth = yy_sg
            itp = interp1d(x, LA_strain_longitud_2ch)
            yy_sg = savgol_filter(itp(xx), window_size, poly_order)
            LA_strain_longitud_2ch_smooth = yy_sg
            np.savetxt(os.path.join(
                results_dir, 'LA_strain_circum_2Ch_smooth.txt'), LA_strain_circum_2Ch_smooth)
            np.savetxt(os.path.join(
                results_dir, 'LA_strain_longitud_2ch_smooth.txt'), LA_strain_longitud_2ch_smooth)
    else:
        QC_atria_2Ch = 1

    # Save 2ch dict and atrial points to avoid recomupting
    if save_2ch_dict_flag and QC_atria_2Ch == 0:
        dict_2ch = {}
        dict_2ch['la_diams_2Ch'] = la_diams_2Ch
        dict_2ch['length_top_2Ch'] = length_top_2Ch
        dict_2ch['LA_circumf_2Ch'] = LA_circumf_2Ch

        np.save(dict_2ch_file, dict_2ch)
        np.save(os.path.join(
            results_dir, f'{study_ID}_LV_atria_points_2Ch.npy'),
            LV_atria_points_2Ch)
        np.save(os.path.join(results_dir, 'points_LV_2Ch.npy'),
                points_LV_2Ch)

    # =====================================================================
    # Compute 2ch volume
    # =====================================================================
    if QC_atria_2Ch == 0:
        LA_volume_area_2ch = np.zeros(N_frames_2Ch)
        LA_volume_SR_2ch = np.zeros(N_frames_2Ch)
        for fr in range(N_frames_2Ch):
            # Simpson's rule
            d1d2 = la_diams_2Ch[fr, :] * la_diams_2Ch[fr, :]
            length = np.min([length_top_2Ch[fr], length_top_2Ch[fr]])
            LA_volume_SR_2ch[fr] = math.pi / 4 * length * \
                np.sum(d1d2) / Nsegments_length / 1000

            # Area method
            LA_volume_area_2ch[fr] = 0.85 * area_LA_2Ch[fr] * \
                area_LA_2Ch[fr] / length / 1000

        x = np.linspace(0, N_frames_2Ch - 1, N_frames_2Ch)
        xx = np.linspace(np.min(x), np.max(x), N_frames_2Ch)
        itp = interp1d(x, LA_volume_SR_2ch)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_SR_2ch_smooth = yy_sg
        itp = interp1d(x, LA_volume_area_2ch)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_area_2ch_smooth = yy_sg

        np.savetxt(os.path.join(
            results_dir, 'LA_volume_SR_2ch.txt'), LA_volume_SR_2ch)
        np.savetxt(os.path.join(
            results_dir, 'LA_volume_SR_2ch_smooth.txt'),
            LA_volume_SR_2ch_smooth)
        np.savetxt(os.path.join(
            results_dir, 'LA_volume_area_2ch.txt'), LA_volume_area_2ch)
        np.savetxt(os.path.join(
            results_dir, 'LA_volume_area_2ch_smooth.txt'),
            LA_volume_area_2ch_smooth)
    else:
        LA_volume_SR_2ch_smooth = np.zeros(20)
        LA_volume_area_2ch_smooth = np.zeros(20)

    # =========================================================================
    # la_4Ch - calculate area and points
    # =========================================================================
    filename_la_seg_4Ch = os.path.join(subject_dir, 'la_4Ch_seg_nnUnet.nii.gz')
    if os.path.exists(filename_la_seg_4Ch):
        nim = nib.load(filename_la_seg_4Ch)
        la_seg_4Ch = nim.get_fdata()
        dx, dy, dz = nim.header['pixdim'][1:4]
        area_per_voxel = dx * dy
        if len(la_seg_4Ch.shape) == 4:
            la_seg_4Ch = la_seg_4Ch[:, :, 0, :]
        la_seg_4Ch = np.transpose(la_seg_4Ch, [1, 0, 2])
        X, Y, N_frames_4Ch = la_seg_4Ch.shape

        # Get largest connected components
        for fr in range(N_frames_4Ch):
            la_seg_4Ch[:, :, fr] = getLargestCC(la_seg_4Ch[:, :, fr])

        # Compute 4ch area using number of pixels
        area_LA_4Ch = np.zeros(N_frames_4Ch)
        area_RA = np.zeros(N_frames_4Ch)  # LA_4Ch
        for fr in range(N_frames_4Ch):
            area_LA_4Ch[fr] = np.sum(
                np.squeeze(
                    la_seg_4Ch[:, :, fr] == 4).astype(float)) * area_per_voxel
            area_RA[fr] = np.sum(np.squeeze(la_seg_4Ch[:, :, fr] == 5).astype(
                float)) * area_per_voxel  # in mm2

        # Compute 4ch params needed for simpson's rule
        save_4ch_LA_dict_flag = False  # Whether to save 4ch dict and points
        save_4ch_RA_dict_flag = False
        dict_4ch_LA_file = os.path.join(  # dict of length values - LA
            results_dir, f'{study_ID}_4ch_LA_length_dict.npy')
        dict_4ch_RA_file = os.path.join(  # dict of length values - RA
            results_dir, f'{study_ID}_4ch_RA_length_dict.npy')
        if os.path.exists(dict_4ch_LA_file):
            # If already saved, load the dictionary
            dict_4ch_LA = np.load(dict_4ch_LA_file, allow_pickle=True).item()
            la_diams_4Ch = dict_4ch_LA['la_diams_4Ch']
            length_top_4Ch = dict_4ch_LA['length_top_4Ch']
            LA_circumf_4Ch = dict_4ch_LA['LA_circumf_4Ch']
        else:
            # Otherwise calculate and save points
            save_4ch_LA_dict_flag = True
            la_diams_4Ch = np.zeros((N_frames_4Ch, Nsegments_length))
            length_top_4Ch = np.zeros(N_frames_4Ch)
            LA_circumf_cycle_4Ch = np.zeros(N_frames_4Ch)
            points_LV_4Ch = np.zeros((N_frames_4Ch, 4, 2))
            LV_atria_points_4Ch = np.zeros((N_frames_4Ch, 9, 2))

            for fr in range(N_frames_4Ch):
                try:
                    apex, mid_valve, anterior, inferior = detect_LV_points(
                        la_seg_4Ch[:, :, fr], logger)
                    points = np.vstack([apex, mid_valve, anterior, inferior])
                    points_LV_4Ch[fr, :] = points
                except Exception:
                    logger.error(
                        'Problem detecting LV points {study_ID}'
                        'in la_4Ch fr {fr}')
                    QC_atria_4Ch_LA = 1

                if QC_atria_4Ch_LA == 0:
                    # LA/LV points
                    try:
                        la_dia, lentop, lenperp, points_non_rotate, contours_LA, lines_LV, points_LV = \
                            get_left_atrial_volumes(
                                la_seg_4Ch[:, :, fr], 'la_4Ch', fr, points, logger)
                        la_diams_4Ch[fr, :] = la_dia * dx
                        length_top_4Ch[fr] = lentop * dx
                        # final_mid_avalve
                        LV_atria_points_4Ch[fr, 0, :] = points_non_rotate[0, :]
                        # final_top_atria
                        LV_atria_points_4Ch[fr, 1, :] = points_non_rotate[1, :]
                        # final_perp_top_atria
                        LV_atria_points_4Ch[fr, 2, :] = points_non_rotate[2, :]
                        # final_atrial_edge1
                        LV_atria_points_4Ch[fr, 3, :] = points_non_rotate[3, :]
                        # final_atrial_edge2
                        LV_atria_points_4Ch[fr, 4, :] = points_non_rotate[4, :]
                        LV_atria_points_4Ch[fr, 5, :] = points_LV[0, :]  # apex
                        # mid_valve
                        LV_atria_points_4Ch[fr, 6, :] = points_LV[1, :]
                        # lateral_4Ch
                        LV_atria_points_4Ch[fr, 7, :] = points_LV[2, :]
                        # septal_4Ch
                        LV_atria_points_4Ch[fr, 8, :] = points_LV[3, :]
                        # compute atrial circumference
                        LA_circumf_4Ch = get_LeftAtrial_circumference(contours_LA, [points_non_rotate[3, 1], points_non_rotate[3, 0]], [
                            points_non_rotate[4, 1], points_non_rotate[4, 0]], [points_non_rotate[1, 1], points_non_rotate[1, 0]], fr, study_ID)
                        LA_circumf_len_4Ch = LA_circumf_4Ch * dx
                        LA_circumf_cycle_4Ch[fr] = LA_circumf_len_4Ch
                    except Exception:
                        logger.error('Problem in disk-making with subject {} in la_4Ch fr {}'.
                                     format(study_ID, fr))
                        QC_atria_4Ch_LA = 1

        if os.path.exists(dict_4ch_RA_file):
            dict_4ch_RA = np.load(dict_4ch_RA_file, allow_pickle=True).item()
            la_diams_RV = dict_4ch_RA['la_diams_RV']
            length_top_RV = dict_4ch_RA['length_top_RV']
            RA_circumf_4Ch = dict_4ch_RA['RA_circumf_4Ch']
        else:
            # Otherwise calculate and save points
            save_4ch_RA_dict_flag = True
            la_diams_RV = np.zeros((N_frames_4Ch, Nsegments_length))  # LA_4Ch
            length_top_RV = np.zeros(N_frames_4Ch)  # LA_4Ch
            RA_circumf_cycle_4Ch = np.zeros(N_frames_4Ch)
            points_RV_4Ch = np.zeros((N_frames_4Ch, 3, 2))
            RV_atria_points_4Ch = np.zeros((N_frames_4Ch, 8, 2))

            for fr in range(N_frames_4Ch):
                try:
                    apex_RV, rvlv_point, free_rv_point = detect_RV_points(
                        la_seg_4Ch[:, :, fr], anterior, logger)
                    pointsRV = np.vstack([apex_RV, rvlv_point, free_rv_point])
                    points_RV_4Ch[fr, :] = pointsRV
                except Exception:
                    logger.error(
                        'Problem detecting RV points {study_ID}'
                        'in la_4Ch fr {fr}')
                    QC_atria_4Ch_RA = 1

                if QC_atria_4Ch_RA == 0:
                    # RA/RV points
                    try:
                        la_dia, lentop, lenperp, points_non_rotate, contours_RA, RA_tapse_seq[fr] = \
                            get_right_atrial_volumes(
                                la_seg_4Ch[:, :, fr], fr, pointsRV, logger)

                        la_diams_RV[fr, :] = la_dia * dx
                        length_top_RV[fr] = lentop * dx

                        # final_mid_avalve
                        RV_atria_points_4Ch[fr, 0, :] = points_non_rotate[0, :]
                        # final_top_atria
                        RV_atria_points_4Ch[fr, 1, :] = points_non_rotate[1, :]
                        # final_perp_top_atria
                        RV_atria_points_4Ch[fr, 2, :] = points_non_rotate[2, :]
                        # final_atrial_edge1
                        RV_atria_points_4Ch[fr, 3, :] = points_non_rotate[3, :]
                        # final_atrial_edge2
                        RV_atria_points_4Ch[fr, 4, :] = points_non_rotate[4, :]
                        RV_atria_points_4Ch[fr, 5,
                                            :] = pointsRV[0, :]  # apex_RV
                        # rvlv_point
                        RV_atria_points_4Ch[fr, 6, :] = pointsRV[1, :]
                        # free_rv_point
                        RV_atria_points_4Ch[fr, 7, :] = pointsRV[2, :]
                        # compute atrial circumference
                        RA_circumf_4Ch = get_LeftAtrial_circumference(contours_RA, [points_non_rotate[3, 1], points_non_rotate[3, 0]], [
                            points_non_rotate[4, 1], points_non_rotate[4, 0]], [points_non_rotate[1, 1], points_non_rotate[1, 0]], fr, study_ID)
                        RA_circumf_len_4Ch = RA_circumf_4Ch * dx
                        RA_circumf_cycle_4Ch[fr] = RA_circumf_len_4Ch
                    except Exception:
                        logger.error(
                            'RV Problem in disk-making with subject {} in la_4Ch fr {}'.format(study_ID, fr))
                        QC_atria_4Ch_RA = 1

        # =====================================================================
        # 4ch Strain
        # =====================================================================
        if QC_atria_4Ch_LA == 0:
            LA_strain_circum_4Ch = get_strain(LA_circumf_cycle_4Ch)
            LA_strain_longitud_4Ch = get_strain(length_top_4Ch)
            
            x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
            xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
            itp = interp1d(x, LA_strain_circum_4Ch)
            yy_sg = savgol_filter(itp(xx), window_size, poly_order)
            LA_strain_circum_4Ch_smooth = yy_sg
            itp = interp1d(x, LA_strain_longitud_4Ch)
            yy_sg = savgol_filter(itp(xx), window_size, poly_order)
            LA_strain_longitud_4Ch_smooth = yy_sg

            np.savetxt(os.path.join(
                results_dir, 'LA_strain_smooth_4Ch.txt'),
                LA_strain_circum_4Ch_smooth)
            
            np.savetxt(os.path.join(
                results_dir, 'LA_strain_longitud_4Ch_smooth.txt'),
                LA_strain_longitud_4Ch_smooth)
            
        if QC_atria_4Ch_RA == 0:
            RA_strain_circum_4Ch = get_strain(RA_circumf_cycle_4Ch)
            RA_strain_longitud_4Ch = get_strain(length_top_RV)

            x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
            xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
            itp = interp1d(x, RA_strain_circum_4Ch)
            yy_sg = savgol_filter(itp(xx), window_size, poly_order)
            RA_strain_circum_4Ch_smooth = yy_sg
            itp = interp1d(x, RA_strain_longitud_4Ch)
            yy_sg = savgol_filter(itp(xx), window_size, poly_order)
            RA_strain_longitud_4Ch_smooth = yy_sg

            np.savetxt(os.path.join(
                results_dir, 'RA_strain_smooth_4Ch.txt'),
                RA_strain_circum_4Ch_smooth)
            np.savetxt(os.path.join(
                results_dir, 'RA_strain_longitud_4Ch_smooth.txt'),
                RA_strain_longitud_4Ch_smooth)

    else:
        QC_atria_4Ch_LA = 1
        # RA_strain_circum_4Ch_smooth = -1*np.ones(20)
        # LA_strain_circum_4Ch_smooth = -1*np.ones(20)
        # RA_strain_longitud_4Ch_smooth = -1*np.ones(20)
        # LA_strain_longitud_4Ch_smooth = -1*np.ones(20)

    # Save 4ch atrial points to avoid recomupting
    if save_4ch_LA_dict_flag and QC_atria_4Ch_LA == 0:
        dict_4ch_LA = {}
        dict_4ch_LA['la_diams_4Ch'] = la_diams_4Ch
        dict_4ch_LA['length_top_4Ch'] = length_top_4Ch
        dict_4ch_LA['LA_circumf_4Ch'] = LA_circumf_4Ch

        np.save(dict_4ch_LA_file, dict_4ch_LA)
        np.save(os.path.join(results_dir, '{}_LV_atria_points_4Ch'.format(
            study_ID)), LV_atria_points_4Ch)
        np.save(os.path.join(results_dir, 'points_LV_4Ch'), points_LV_4Ch)

    if save_4ch_RA_dict_flag and QC_atria_4Ch_RA == 0:
        dict_4ch_RA = {}
        dict_4ch_RA['la_diams_RV'] = la_diams_RV
        dict_4ch_RA['length_top_RV'] = length_top_RV
        dict_4ch_RA['RA_circumf_4Ch'] = RA_circumf_4Ch
        np.save(dict_4ch_RA_file, dict_4ch_RA)
        np.save(os.path.join(results_dir, '{}_RV_atria_points_4Ch'.format(
            study_ID)), RV_atria_points_4Ch)
        np.save(os.path.join(results_dir, 'points_RV_4Ch'), points_RV_4Ch)

    # =====================================================================
    # Compute 4ch volume
    # =====================================================================
    # LA volumes
    if QC_atria_4Ch_LA == 0:
        LA_volume_SR_4Ch = np.zeros(N_frames_4Ch)
        LA_volume_area_4ch = np.zeros(N_frames_4Ch)
        for fr in range(N_frames_4Ch):
            # Simpson's rule
            d1d2 = la_diams_4Ch[fr, :] * la_diams_4Ch[fr, :]
            length = np.min([length_top_4Ch[fr], length_top_4Ch[fr]])
            LA_volume_SR_4Ch[fr] = math.pi / 4 * length * \
                np.sum(d1d2) / Nsegments_length / 1000

            # Area method
            LA_volume_area_4ch[fr] = 0.85 * area_LA_4Ch[fr] * \
                area_LA_4Ch[fr] / length / 1000

        x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
        xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
        itp = interp1d(x, LA_volume_SR_4Ch)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_SR_4Ch_smooth = yy_sg
        itp = interp1d(x, LA_volume_area_4ch)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_area_4ch_smooth = yy_sg

        np.savetxt(os.path.join(
            results_dir, 'LA_volume_SR_4Ch.txt'), LA_volume_SR_4Ch)
        np.savetxt(os.path.join(
            results_dir, 'LA_volume_SR_4Ch_smooth.txt'),
            LA_volume_SR_4Ch_smooth)
        np.savetxt(os.path.join(
            results_dir, 'LA_volume_area_4ch.txt'), LA_volume_area_4ch)
        np.savetxt(os.path.join(
            results_dir, 'LA_volume_area_4ch_smooth.txt'),
            LA_volume_area_4ch_smooth)

    # RA volumes  
    if QC_atria_4Ch_RA == 0:
        RA_volumes_SR = np.zeros(N_frames_4Ch)
        RA_volumes_area = np.zeros(N_frames_4Ch)
        for fr in range(N_frames_4Ch):
            d1d2 = la_diams_RV[fr, :] * la_diams_RV[fr, :]
            length = length_top_RV[fr]
            RA_volumes_SR[fr] = math.pi / 4 * length * \
                np.sum(d1d2) / Nsegments_length / 1000
            RA_volumes_area[fr] = 0.85 * area_RA[fr] * \
                area_RA[fr] / length / 1000
        
        x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
        xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
        itp = interp1d(x, RA_volumes_SR)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        RA_volumes_SR_smooth = yy_sg
        itp = interp1d(x, RA_volumes_area)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        RA_volumes_area_smooth = yy_sg

        np.savetxt(os.path.join(
            results_dir, 'RA_volumes_SR.txt'), RA_volumes_SR)
        np.savetxt(os.path.join(
            results_dir, 'RA_volumes_area.txt'), RA_volumes_area)
        np.savetxt(os.path.join(
            results_dir, 'RA_volumes_SR_smooth.txt'), RA_volumes_SR_smooth)
        np.savetxt(os.path.join(
            results_dir, 'RA_volumes_area_smooth.txt'), RA_volumes_area_smooth)
    # else:
    #     LA_volume_SR_4Ch_smooth = np.zeros(20)
    #     RA_volumes_area_smooth = np.zeros(20)
    #     RA_volumes_SR_smooth = np.zeros(20)

    # =====================================================================
    # Compute volume by combining 2ch and 4ch views
    # =====================================================================
    if QC_atria_4Ch_LA == 0 and QC_atria_2Ch == 0 and N_frames_2Ch == N_frames_4Ch:
        LA_volume_combined_SR = np.zeros(N_frames_4Ch)
        LA_volume_combined_area = np.zeros(N_frames_4Ch)

        # Combined volume based on Simpson's rule
        for fr in range(N_frames_4Ch):
            d1d2 = la_diams_2Ch[fr, :] * la_diams_4Ch[fr, :]
            length = np.min([length_top_2Ch[fr], length_top_4Ch[fr]])
            LA_volume_combined_SR[fr] = math.pi / 4 * length * \
                np.sum(d1d2) / Nsegments_length / 1000

        # Combined volume based on number of pixels
        if N_frames_2Ch == N_frames_4Ch:
            LA_volume_combined_area[fr] = 0.85 * area_LA_2Ch[fr] * \
                area_LA_4Ch[fr] / length / 1000

        x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
        xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
        itp = interp1d(x, LA_volume_combined_SR)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_combined_SR_smooth = yy_sg

        itp = interp1d(x, LA_volume_combined_area)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_combined_area_smooth = yy_sg

        # =====================================================================
        # Calculate combined strain using 2ch and 4ch views
        # =====================================================================
        LA_strain_circum_combined = LA_strain_circum_4Ch_smooth +\
            LA_strain_circum_2Ch / 2
        LA_strain_longitud_combined = LA_strain_longitud_4Ch_smooth +\
            LA_strain_longitud_2ch / 2

        np.savetxt(os.path.join(results_dir, 'LA_volume_combined_SR.txt'),
                   LA_volume_combined_SR)
        np.savetxt(os.path.join(results_dir, 'LA_volume_combined_area.txt'),
                   LA_volume_combined_area)
        np.savetxt(os.path.join(results_dir,
                                'LA_volume_combined_SR_smooth.txt'),
                   LA_volume_combined_SR_smooth)
        np.savetxt(os.path.join(results_dir,
                                'LA_volume_combined_area_smooth.txt'),
                   LA_volume_combined_area_smooth)
        np.savetxt(os.path.join(results_dir, 'LA_strain_circum_combined.txt'),
                   LA_strain_circum_combined)
        np.savetxt(os.path.join(results_dir, 'LA_strain_longitud_combined.txt'),
                   LA_strain_longitud_combined)

    # =========================================================================
    # Compute params if not the same number of slices between views
    # =========================================================================
    elif QC_atria_4Ch_LA == 0 and QC_atria_2Ch == 0 and N_frames_2Ch != N_frames_4Ch:
        max_frames = max(N_frames_2Ch, N_frames_4Ch)
        length_top_2Ch_itp = resample(length_top_2Ch, max_frames)
        length_top_4Ch_itp = resample(length_top_4Ch, max_frames)
        area_LA_2Ch_itp = resample(area_LA_2Ch, max_frames)
        area_LA_4Ch_itp = resample(area_LA_4Ch, max_frames)
        la_diams_2Ch_itp = resample(la_diams_2Ch, max_frames)
        la_diams_4Ch_itp = resample(la_diams_4Ch, max_frames)

        LA_volume_combined_SR = np.zeros(max_frames)
        LA_volume_combined_area = np.zeros(max_frames)

        for fr in range(max_frames):
            # Simpson's rule
            d1d2 = la_diams_2Ch_itp[fr, :] * la_diams_4Ch_itp[fr, :]
            length = np.min([length_top_2Ch_itp[fr], length_top_4Ch_itp[fr]])
            LA_volume_combined_SR[fr] = math.pi / 4 * length * \
                np.sum(d1d2) / Nsegments_length / 1000

            # Pixel method
            if N_frames_2Ch == N_frames_4Ch:
                LA_volume_combined_area[fr] = 0.85 * area_LA_2Ch_itp[fr] * \
                    area_LA_4Ch_itp[fr] / length / 1000

        x = np.linspace(0, max_frames - 1, max_frames)
        xx = np.linspace(np.min(x), np.max(x), max_frames)
        itp = interp1d(x, LA_volume_combined_SR)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_combined_SR_smooth = yy_sg

        itp = interp1d(x, LA_volume_combined_area)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volume_combined_area_smooth = yy_sg
        LA_strain_circum_combined = np.zeros(20)
        LA_strain_longitud_combined = np.zeros(20)

        np.savetxt(os.path.join(results_dir, 'LA_volume_combined_SR.txt'),
                   LA_volume_combined_SR)
        np.savetxt(os.path.join(results_dir, 'LA_volume_combined_area.txt'),
                   LA_volume_combined_area)
        np.savetxt(os.path.join(results_dir,
                                'LA_volume_combined_SR_smooth.txt'),
                   LA_volume_combined_SR_smooth)
        np.savetxt(os.path.join(results_dir,
                                'LA_volume_combined_area_smooth.txt'),
                   LA_volume_combined_area_smooth)
        np.savetxt(os.path.join(results_dir, 'LA_strain_smooth.txt'),
                   LA_strain_circum_combined)
        np.savetxt(os.path.join(results_dir,
                                'LA_strain_longitud_combined.txt'),
                   LA_strain_longitud_combined)
    else:
        LA_volume_combined_SR_smooth = np.zeros(20)
        LA_volume_combined_area_smooth = np.zeros(20)
        LA_strain_circum_combined = np.zeros(20)

    # =========================================================================
    # Peak volume
    # =========================================================================
    peak_LA_volume_area_2ch = LA_volume_area_2ch_smooth.max()
    peak_LA_volume_SR_2ch = LA_volume_SR_2ch_smooth.max()
    peak_LA_volume_area_4ch = LA_volume_area_4ch_smooth.max()
    peak_LA_volume_SR_4ch = LA_volume_SR_4Ch_smooth.max()
    peak_LA_volume_area_combined = LA_volume_combined_area.max()
    peak_LA_volume_SR_combined = LA_volume_combined_SR.max()
    peak_RA_volume_area = RA_volumes_area_smooth.max()
    peak_RA_volume_SR = RA_volumes_SR_smooth.max()

    # =========================================================================
    # Peak strain
    # =========================================================================
    peak_LA_strain_circum_2ch_max = LA_strain_circum_2Ch.max()
    peak_LA_strain_longitud_2ch_max = LA_strain_longitud_2ch.max()
    peak_LA_strain_circum_4ch_max = LA_strain_circum_4Ch_smooth.max()
    peak_LA_strain_longitud_4ch_max = LA_strain_longitud_4Ch_smooth.max()
    peak_LA_strain_circum_combined_max = LA_strain_circum_combined.max()
    peak_LA_strain_longitud_combined_max = LA_strain_longitud_combined.max()
    peak_RA_strain_circum_max = RA_strain_circum_4Ch_smooth.max()
    peak_RA_strain_longitud_max = RA_strain_longitud_4Ch_smooth.max()

    ES_frame = LA_volume_combined_SR_smooth.argmax()
    peak_LA_strain_circum_2ch_ES = LA_strain_circum_2Ch[ES_frame]
    peak_LA_strain_longitud_2ch_ES = LA_strain_longitud_2ch[ES_frame]
    peak_LA_strain_circum_4ch_ES = LA_strain_circum_4Ch_smooth[ES_frame]
    peak_LA_strain_longitud_4ch_ES = LA_strain_longitud_4Ch_smooth[ES_frame]
    peak_LA_strain_circum_combined_ES = LA_strain_circum_combined[ES_frame]
    peak_LA_strain_longitud_combined_ES = LA_strain_longitud_combined[ES_frame]

    ES_frame_RA = RA_volumes_SR_smooth.argmax()
    peak_RA_strain_circum_ES = RA_strain_circum_4Ch_smooth[ES_frame_RA]
    peak_RA_strain_longitud_ES = RA_strain_longitud_4Ch_smooth[ES_frame_RA]

    # =========================================================================
    # PLOTS
    # =========================================================================
    plt.figure()
    plt.plot(LA_volume_SR_2ch_smooth, label='Simpson - 2Ch')
    plt.plot(LA_volume_SR_4Ch_smooth, label='Simpson - 4Ch')
    plt.plot(LA_volume_area_2ch_smooth, label='Area - 2Ch')
    plt.plot(LA_volume_area_4ch_smooth, label='Area - 4Ch')
    plt.plot(LA_volume_combined_SR_smooth, label='Simpson - combined')
    plt.plot(LA_volume_combined_area_smooth, label='Area method - combined')
    plt.legend()
    plt.title('Left Atrial Volume')
    plt.savefig(os.path.join(results_dir, 'LA_volume.png'))
    plt.close('all')

    plt.figure()
    plt.plot(RA_volumes_SR_smooth, label='Simpson method')
    plt.plot(RA_volumes_area_smooth, label='Area method')
    plt.legend()
    plt.title('Right Atrial Volume')
    plt.savefig(os.path.join(results_dir, 'RA_volume.png'))
    plt.close('all')

    # interpolation
    interp_folder = '/motion_repository/UKBiobank/AICMRQC_analysis/log/interp'
    if not os.path.exists(interp_folder):
        os.mkdir(interp_folder)
    x_2ch = np.arange(N_frames_2Ch)
    x_4ch = np.arange(N_frames_4Ch)
    plt.figure()
    plt.plot(LA_volume_SR_2ch_smooth)
    plt.plot(x_2ch, LA_volume_SR_2ch, 's')
    plt.legend()
    plt.title('LA volume Simpson 2ch')
    plt.savefig(os.path.join(interp_folder,
                f'LA_vol_Simpson2ch_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(LA_volume_SR_4Ch_smooth)
    plt.plot(x_4ch, LA_volume_SR_4Ch, 's')
    plt.legend()
    plt.title('LA volume Simpson 4ch')
    plt.savefig(os.path.join(interp_folder,
                'LA_vol_Simpson4ch_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(LA_volume_area_2ch_smooth)
    plt.plot(x_2ch, LA_volume_area_2ch, 's')
    plt.legend()
    plt.title('LA volume area 2ch')
    plt.savefig(os.path.join(interp_folder, 'LA_vol_Area2ch_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(LA_volume_area_4ch_smooth)
    plt.plot(x_4ch, LA_volume_area_4ch, 's')
    plt.legend()
    plt.title('LA volume area 4ch')
    plt.savefig(os.path.join(interp_folder, 'LA_vol_Area4ch_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(LA_volume_combined_SR_smooth)
    plt.plot(x_2ch, LA_volume_combined_SR, 's')
    plt.legend()
    plt.title('LA volume Simpson combined')
    plt.savefig(os.path.join(interp_folder,
                'LA_vol_SimpsonCombined_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(LA_volume_combined_area_smooth)
    plt.plot(x_4ch, LA_volume_combined_area, 's')
    plt.legend()
    plt.title('LA volume area combined')
    plt.savefig(os.path.join(interp_folder,
                'LA_vol_AreaCombined_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(RA_volumes_SR_smooth)
    plt.plot(x_4ch, RA_volumes_SR, 's')
    plt.legend()
    plt.title('RA volume SR')
    plt.savefig(os.path.join(interp_folder,
                'RA_vol_SR_{study_ID}.png'))
    plt.close('all')

    plt.figure()
    plt.plot(RA_volumes_area_smooth)
    plt.plot(x_4ch, RA_volumes_area, 's')
    plt.legend()
    plt.title('RA volume area')
    plt.savefig(os.path.join(interp_folder,
                'RA_vol_Area_{study_ID}.png'))
    plt.close('all')

    try:
        # Circumferential strain
        plt.figure()
        plt.plot(LA_strain_circum_2Ch, 's')
        plt.plot(LA_strain_circum_2Ch, label='2ch')
        plt.plot(LA_strain_circum_2Ch.argmax(),
                 peak_LA_strain_circum_2ch_max, 'ro', label='Peak strain- max')
        plt.plot(
            ES_frame, peak_LA_strain_circum_2ch_ES, 'b*', label='Peak strain - ES')
        plt.plot(x_4ch, LA_strain_circum_4Ch, 'ko')
        plt.plot(LA_strain_circum_4Ch_smooth, 'k', label='4ch')
        plt.plot(LA_strain_circum_4Ch_smooth.argmax(),
                 peak_LA_strain_circum_4ch_max, 'ro')
        plt.plot(ES_frame, peak_LA_strain_circum_4ch_ES, 'b*')
        plt.plot(LA_strain_circum_combined, label='Combined')
        plt.plot(LA_strain_circum_combined.argmax(),
                 peak_LA_strain_circum_combined_max, 'ro')
        plt.plot(ES_frame, peak_LA_strain_circum_combined_ES, 'b*')
        plt.legend()
        plt.title('LA Circumferential Strain')
        plt.savefig(os.path.join(results_dir, 'LA_circum_strain.png'))
        plt.close('all')

        # Longitudinal strain
        plt.figure()
        plt.plot(LA_strain_longitud_2ch, label='2ch')
        plt.plot(LA_strain_longitud_2ch.argmax(),
                 peak_LA_strain_longitud_2ch_max, 'ro',
                 label='Peak strain- max')
        plt.plot(ES_frame, peak_LA_strain_longitud_2ch_ES,
                 'b*', label='Peak strain - ES')
        plt.plot(LA_strain_longitud_4Ch_smooth, label='4ch')
        plt.plot(LA_strain_longitud_4Ch_smooth.argmax(),
                 peak_LA_strain_longitud_4ch_max, 'ro')
        plt.plot(ES_frame, peak_LA_strain_longitud_4ch_ES, 'b*')
        plt.plot(LA_strain_longitud_combined, label='Combined')
        plt.plot(LA_strain_longitud_combined.argmax(),
                 peak_LA_strain_longitud_combined_max, 'ro')
        plt.plot(ES_frame, peak_LA_strain_longitud_combined_ES, 'b*')
        plt.legend()
        plt.title('LA Longitudinal Strain')
        plt.savefig(os.path.join(results_dir, 'LA_longitud_strain.png'))
        plt.close('all')

        # RA strain
        plt.figure()
        plt.plot(RA_strain_circum_4Ch_smooth, label='Circum')
        plt.plot(RA_strain_circum_4Ch_smooth.argmax(),
                 peak_RA_strain_circum_max, 'ro', label='Peak strain- max')
        plt.plot(ES_frame_RA, peak_RA_strain_circum_ES, 'b*',
                 label='Peak strain - ES')
        plt.plot(RA_strain_longitud_4Ch_smooth, label='Longitud')
        plt.plot(RA_strain_longitud_4Ch_smooth.argmax(),
                 peak_RA_strain_longitud_max, 'ro')
        plt.plot(ES_frame_RA, peak_RA_strain_longitud_ES, 'b*')
        plt.legend()
        plt.title('RA Strain')
        plt.savefig(os.path.join(results_dir, 'RA_strain.png'))
        plt.close('all')

        # interpolate
        plt.figure()
        plt.plot(LA_strain_circum_2Ch_smooth)
        plt.plot(x_2ch, LA_strain_circum_2Ch, 's')
        plt.legend()
        plt.title('LA strain circum 2ch')
        plt.savefig(os.path.join(interp_folder,
                    'LA_strain_circum2ch_{study_ID}.png'))
        plt.close('all')

        plt.figure()
        plt.plot(LA_strain_circum_4Ch_smooth)
        plt.plot(x_4ch, LA_strain_circum_4Ch, 's')
        plt.legend()
        plt.title('LA strain circum 4ch')
        plt.savefig(os.path.join(interp_folder,
                    'LA_strain_circum4ch_{study_ID}.png'))
        plt.close('all')

        plt.figure()
        plt.plot(LA_strain_longitud_2ch_smooth)
        plt.plot(x_2ch, LA_strain_longitud_2ch, 's')
        plt.legend()
        plt.title('LA strain longitud 2ch')
        plt.savefig(os.path.join(interp_folder,
                    'LA_strain_longitud2ch_{study_ID}.png'))
        plt.close('all')

        plt.figure()
        plt.plot(LA_strain_longitud_4Ch)
        plt.plot(x_4ch, LA_strain_longitud_4Ch_smooth, 's')
        plt.legend()
        plt.title('LA strain longitud 4ch')
        plt.savefig(os.path.join(interp_folder,
                    'LA_strain_longitud4ch_{study_ID}.png'))
        plt.close('all')

        plt.figure()
        plt.plot(RA_strain_circum_4Ch_smooth)
        plt.plot(x_2ch, RA_strain_circum_4Ch, 's')
        plt.legend()
        plt.title('RA strain circum')
        plt.savefig(os.path.join(interp_folder,
                    'RA_strain_circum_{study_ID}.png'))
        plt.close('all')

        plt.figure()
        plt.plot(RA_strain_longitud_4Ch_smooth)
        plt.plot(x_4ch, RA_strain_longitud_4Ch, 's')
        plt.legend()
        plt.title('RA strain longitud')
        plt.savefig(os.path.join(interp_folder,
                    'RA_strain_longitud_{study_ID}.png'))
        plt.close('all')

        # f, ax = plt.subplots()
        # ax.plot(RA_strain_circum_4Ch_smooth)
        # ax.plot(RA_strain_circum_4Ch_smooth.argmax(),
        #         RA_strain_circum_4Ch_smooth[RA_strain_circum_4Ch_smooth.argmax()], 'ro')
        # ax.annotate('peak RA strain', (RA_strain_circum_4Ch_smooth.argmax(),
        #             RA_strain_circum_4Ch_smooth[RA_strain_circum_4Ch_smooth.argmax()]))
        # ax.set_title('{}: RA strain 4Ch'.format(study_ID))
        # f.savefig(os.path.join(results_dir, 'RA_strain_circum_4Ch.png'))
        # plt.close('all')

    except Exception:
        logger.error(
            'Problem in calculating strain with subject {}'.format(study_ID))
        QC_atria_4Ch_LA = 1

    # =========================================================================
    # SAVE RESULTS
    # =========================================================================
    vols = -1*np.ones(25, dtype=object)
    vols[0] = study_ID
    vols[1] = peak_LA_volume_area_2ch
    vols[2] = peak_LA_volume_SR_2ch
    vols[3] = peak_LA_volume_area_4ch
    vols[4] = peak_LA_volume_SR_4ch
    vols[5] = peak_LA_volume_area_combined
    vols[6] = peak_LA_volume_SR_combined

    vols[7] = peak_LA_strain_circum_2ch_ES
    vols[8] = peak_LA_strain_circum_2ch_max
    vols[9] = peak_LA_strain_circum_4ch_ES
    vols[10] = peak_LA_strain_circum_4ch_max
    vols[11] = peak_LA_strain_circum_combined_ES
    vols[12] = peak_LA_strain_circum_combined_max

    vols[13] = peak_LA_strain_longitud_2ch_ES
    vols[14] = peak_LA_strain_longitud_2ch_max
    vols[15] = peak_LA_strain_longitud_4ch_ES
    vols[16] = peak_LA_strain_longitud_4ch_max
    vols[17] = peak_LA_strain_longitud_combined_ES
    vols[18] = peak_LA_strain_longitud_combined_max

    vols[19] = peak_RA_volume_area
    vols[20] = peak_RA_volume_SR
    vols[21] = peak_RA_strain_circum_ES
    vols[22] = peak_RA_strain_circum_max
    vols[23] = peak_RA_strain_longitud_ES
    vols[24] = peak_RA_strain_longitud_max

    vols = np.reshape(vols, [1, 25])
    df = pd.DataFrame(vols)
    df.to_csv(os.path.join(results_dir, 'atrial_peak_params.csv'),
              header=['eid', 'LA_vol_area_2ch', 'LA_vol_SR_2ch',
                      'LA_vol_area_4ch', 'LA_vol_SR_4ch', 'LA_vol_area_combo',
                      'LA_vol_SR_combo', 'LA_strain_circum_2ch_ES',
                      'LA_strain_circum_2ch_max', 'LA_strain_circum_4ch_ES',
                      'LA_strain_circum_4ch_max',
                      'LA_strain_circum_combined_ES',
                      'LA_strain_circum_combined_max',
                      'LA_strain_long_2ch_ES', 'LA_strain_long_2ch_max',
                      'LA_strain_long_4ch_ES', 'LA_strain_long_4ch_max',
                      'LA_strain_long_combo_ES', 'LA_strain_long_combo_max',
                      'RA_volume_area', 'RA_volume_SR', 'RA_strain_circum_ES',
                      'RA_strain_circum_max', 'RA_strain_long_ES',
                      'RA_strain_long_max'], index=False)