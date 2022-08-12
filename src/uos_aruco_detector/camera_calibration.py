import argparse
import glob
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


def yaml(size, intrinsics, distortion, num_images, avg_reprojection_error):
    now = datetime.now()
    calmessage = (
        "%YAML:1.0\n"
        + "image_width: "
        + str(size[0])
        + "\n"
        + "image_height: "
        + str(size[1])
        + "\n"
        + "camera_matrix: !!opencv-matrix\n"
        + "  rows: 3\n"
        + "  cols: 3\n"
        + "  dt: d\n"
        + "  data: ["
        + ", ".join(["%8f" % i for i in intrinsics.reshape(1, 9)[0]])
        + "]\n"
        + "distortion_model: "
        + ("rational_polynomial" if distortion.size > 5 else "plumb_bob")
        + "\n"
        + "distortion_coefficients: !!opencv-matrix\n"
        + "  rows: 1\n"
        + "  cols: 5\n"
        + "  dt: d\n"
        + "  data: ["
        + ", ".join(["%8f" % distortion[i, 0] for i in range(distortion.shape[0])])
        + "]\n"
        + 'date: "'
        + now.strftime("%d/%m/%Y %H:%M:%S")
        + '" \n'
        + "number_of_images: "
        + str(num_images)
        + "\n"
        + "avg_reprojection_error: "
        + str(avg_reprojection_error)
        + "\n"
        + ""
    )
    return calmessage


def main():
    parser = argparse.ArgumentParser(description="Calibrate camera using aruco markers")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        help="Folder where the images are stored",
    )
    parser.add_argument(
        "-e", "--extension", type=str, default="jpg", help="image extension"
    )
    parser.add_argument(
        "--nx", type=int, default=9, help="Number of inside corners in x"
    )
    parser.add_argument(
        "--ny", type=int, default=6, help="Number of inside corners in y"
    )
    parser.add_argument(
        "--size", type=float, default=0.03, help="Size of chessboard squares"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=".",
        help="Output directory for calibration results",
    )
    args = parser.parse_args()

    # If no arguments are provided, print help
    if len(sys.argv) == 1:
        parser.print_help()
        print(
            "The script will look for every image in the provided folder and will",
            "show the pattern found.\n",
            "Users can skip the image pressing ESC or accepting the image with RETURN.",
            "At the end the end the following files are created:\n",
            "  - camera_calibration.yaml:\n",
            "      Contains the calibration matrix and distortion coefficients\n",
        )
        sys.exit(1)

    if args.input is None:
        print("Please specify an input folder")
        sys.exit(1)
    if args.nx is None:
        print("Please specify nx")
        sys.exit(1)
    if args.ny is None:
        print("Please specify ny")
        sys.exit(1)
    if args.size is None:
        print("Please specify size")
        sys.exit(1)
    if args.extension is None:
        print("Please specify extension")
        sys.exit(1)

    output_directory = Path(args.output)

    n_rows = args.nx
    n_cols = args.ny
    dimension = args.size
    image_folder = Path(args.input)
    image_extension = args.extension
    images = list(image_folder.glob("*." + image_extension))

    print(
        "Looking for images in {}".format(image_folder),
        "with extension {}".format(image_extension),
    )
    print("Found", len(images), "images")
    if len(images) < 9:
        print("Not enough images were found: at least 9 shall be provided")
        sys.exit()

    # termination criteria
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, dimension, 0.001)

    # prepare object points, like (0,0,0), (1,0,0), (2,0,0) ....,(6,5,0)
    objp = np.zeros((n_rows * n_cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:n_cols, 0:n_rows].T.reshape(-1, 2)

    # Arrays to store object points and image points from all the images.
    objpoints = []  # 3d point in real world space
    imgpoints = []  # 2d points in image plane.

    num_patterns_found = 0
    good_images = []

    for fname in images:
        if "calibresult" in fname:
            continue
        # -- Read the file and convert in greyscale
        img = cv2.imread(fname)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        print("Reading image ", fname)

        # Find the chess board corners
        chessboard_found, corners = cv2.findChessboardCorners(
            gray, (n_cols, n_rows), None
        )

        if not chessboard_found:
            continue

        # If found, add object points, image points (after refining them)
        print("Pattern found! Press ESC to skip or ENTER to accept")
        # --- Sometimes, Harris cornes fails with crappy pictures, so
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        # Draw and display the corners
        cv2.drawChessboardCorners(img, (n_cols, n_rows), corners2, chessboard_found)
        cv2.imshow("img", img)
        k = cv2.waitKey(0) & 0xFF
        if k == 27:  # -- ESC Button
            print("Image Skipped")

        print("Image accepted")
        num_patterns_found += 1
        objpoints.append(objp)
        imgpoints.append(corners2)
        good_images.append(fname)
    cv2.destroyAllWindows()

    num_images = len(good_images)

    print("Found %d good images" % (num_images))

    if num_images < 3:
        print("Not enough good images were found, we need at least 3")
        sys.exit()

    avg_reprojection_error, mtx, distortion, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, gray.shape[::-1], None, None
    )

    # Undistort an image
    img = cv2.imread(good_images[0])
    h, w = img.shape[:2]
    newcameramtx, roi = cv2.getOptimalNewCameraMatrix(
        mtx, distortion, (w, h), 1, (w, h)
    )

    # undistort
    mapx, mapy = cv2.initUndistortRectifyMap(
        mtx, distortion, None, newcameramtx, (w, h), 5
    )
    dst = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)

    size = (w, h)
    intrinsics = newcameramtx

    # crop the image
    x, y, w, h = roi
    dst = dst[y : y + h, x : x + w]
    print("ROI: ", x, y, w, h)
    output_file = str(output_directory / "calib_result.png")
    cv2.imwrite(output_file, dst)
    print("Calibrated picture saved as", output_file)
    print("Calibration Matrix: \n", intrinsics)
    print("Disortion: \n", distortion)

    output_file = output_directory / "camera_calibration.yaml"
    with output_file.open("w") as f:
        f.write(yaml(size, intrinsics, distortion, num_images, avg_reprojection_error))
    print("Calibration data saved as", output_file)


if __name__ == "__main__":
    main()
