#!/usr/bin/env python

# import modules used here -- sys is a very standard one
import sys, time, argparse, logging, requests

# Gather our code in a main() function
def main(args):
  logging.info("readming mjpeg-stream from %s", args.url);
  req = requests.get(args.url, stream=True)
  logging.debug("received headers: %s", req.headers);


  ctype = req.headers["Content-Type"]
  if not ctype.startswith("multipart/x-mixed-replace"):
    logging.error("document content-type is %s, not 'multipart/x-mixed-replace'", ctype)
    return False;


  paramstrs = ctype.split(";")[1:]
  parampairs = [s.split("=", 1) for s in paramstrs]
  params = {k.strip().lower(): v.strip().lower() for k,v in parampairs}
  logging.debug("parsed content-type params: %s", params);

  if not "boundary" in params:
    logging.error("no boundary-param declared in the content-type %s", ctype)
    return False;

  boundary = params["boundary"]
  if len(boundary) < 16:
    logging.warning("boundary is a little shorts (only %u characters)", len(boundary))


  logging.info("boundary parsed: %s", boundary)
  logging.debug("start parsing stream")


  # number of frames seen
  framecount = 0

  # sum of the sizes of frames seen
  framesize_sum = 0

  # sum of the duration in (mili?)seconds of frames seen
  framegap_sum = 0

  jitter_sum = 0

  # durations in (mili?)seconds of frames seen
  framegaps = []


  # size of the last frame (working variable)
  framesize = 0

  # timsestamp of last frame seen (working variable)
  prevframe_stamp = time.time()


  try:
    while True:
      # 1. look for boundary-line
      logging.debug("looking for boundary-line")
      preboundary_size = 0
      while True:
        line = req.raw.readline()
        if line.startswith(boundary) or line.startswith("--" + boundary):
          logging.debug("found boundary-line after %u bytes", preboundary_size)
          break

        preboundary_size += len(line)

      # 1a. add over-read number of bytes to framesize
      framesize += preboundary_size

      # 2. record timing & size-information (if this is not the first boundary)
      if framesize > 0:
        framecount += 1
        framesize_sum += framesize

        framegap = time.time() - prevframe_stamp
        framegap_sum += framegap
        framegaps.append(framegap)

        # statistics of interests:
        #  - avg. framerate,
        #  - current frame jitter
        #  - avg. jitter
        #  - framerate last n frames
        #  - jitter last n frames
        # 1. calculate avg. framerate across all seen frames
        # 2. calculate jitter of current frame
        #
        avg_framerate = 1/(framegap_sum/framecount)
        jitter = framegap - (framegap_sum/framecount)
        jitter_sum += abs(jitter)
        jitterpct = jitter / (framegap_sum/framecount) * 100

        print("framerate averages to %.2f, frame #%u jitters by %.4fs (%.1f%%)" %
          (avg_framerate, framecount, jitter, jitterpct))

        prevframe_stamp = time.time()
        framesize = 0

      # 3. read frame-headers
      frameheaders = {}
      while True:
        line = req.raw.readline().rstrip()
        if len(line) == 0:
          # empty line = enf of header
          break

        k, v = [s.strip().lower() for s in line.split(":", 1)]
        frameheaders[k] = v

      logging.debug("received frame-headers: %s", frameheaders);

      # 4. fail if no length or type is provided or type is wrong
      if not "content-type" in frameheaders:
        logging.warning("no frame content-type provided")

      if frameheaders["content-type"] != "image/jpeg":
        logging.warning("frame content-type is %s, not 'image/jpeg'", frameheaders["content-type"])

      if not "content-length" in frameheaders:
        logging.error("no frame content-length provided")
        return False

      length = int(frameheaders["content-length"])
      if length < 1:
        logging.warning("invalid frame content-length %d provided", length)
        continue

      # 4a. read that amount of bytes
      framedata = req.raw.read(length)

      # 4b. record read length as frame-size
      logging.debug("read %u bytes of frame-data", len(framedata))
      framesize += len(framedata)
  except (KeyboardInterrupt, SystemExit):
    avg_framerate = 1/(framegap_sum/framecount)
    avg_jitter = jitter_sum/framecount
    avg_jitterpct = avg_jitter / (framegap_sum/framecount) * 100

    print("")
    print("final report:")
    print("  avg framerate was %.2f, avg. absolute jitters was %.4fs (%.1f%%)" %
      (avg_framerate, avg_jitter, avg_jitterpct))

    if args.timing_file:
      logging.info("writing frame-times to %s", args.timing_file)
      with open(args.timing_file, "w") as f:
        for framegap in framegaps:
          f.write("%.10f\n" % framegap)
      logging.info("wrote %u lines", len(framegaps))




# setup commandline tool
if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    description="Measure fps and jitter of an MJPEG-Stream")

  parser.add_argument("url",
    help="the http(s) url to read the mjpeg-stream from",
    metavar="ARG")

  parser.add_argument("-t", "--timing-file",
    help="save timings in a file which can be used to replay the mjpeg-stream",
    metavar="FILE")

  parser.add_argument("-v", "--verbose",
    help="increase output verbosity",
    action="store_true")

  args = parser.parse_args()


  # Setup logging
  if args.verbose:
    loglevel = logging.DEBUG
  else:
    loglevel = logging.INFO

  logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)

  # enter main program
  main(args)
