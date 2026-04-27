# Human Next Steps

This file tells you exactly what to do next as the human operator for the current Phase 1 state of the project.

## 1. Your Goal Right Now

Your immediate goal is to validate that the current assumptions about:

- geometry
- crop sizing
- prior uncertainty
- replay packet format
- live packet format

are reasonable for your real drone and camera setup before we invest more code into a richer live loop or localization model.

## 2. What Already Exists

The repo already has these working vertical slices:

- replay packet parsing
- geometry interpretation from altitude, heading, and FOV
- prior-based crop planning
- combined replay pipeline with sensitivity summaries
- minimal live receiver stub for one packet

The AI work is not blocked on scaffolding anymore. The next meaningful progress depends on your review of the generated artifacts and, ideally, your first real or semi-real captured packets.

## 3. First Thing To Do

Run the required verification script:

```powershell
.\scripts\run_pytest_isolation.bat
```

What success looks like:

- the output ends with `verification_ok`
- the script reports geometry, crop, and replay-pipeline artifacts
- the script pauses so you can copy the output

After every future code change, this is the command you should run and paste back into the conversation.

## 4. Inspect The Current Artifacts

Open and inspect these files:

- `artifacts/manual-verification/geometry-report/geometry_debug.svg`
- `artifacts/manual-verification/crop-plan/crop_debug.svg`
- `artifacts/manual-verification/replay-pipeline/pipeline_debug.svg`
- `artifacts/manual-verification/geometry-report/geometry_summary.json`
- `artifacts/manual-verification/crop-plan/crop_summary.json`
- `artifacts/manual-verification/replay-pipeline/pipeline_summary.json`

What to check in `geometry_debug.svg` and `geometry_summary.json`:

- does the ground footprint size look plausible for your expected altitude and camera FOV?
- does the width vs height ratio make sense for your camera aspect ratio?
- does the reported rotation-to-north-up make sense relative to heading?

What to check in `crop_debug.svg` and `crop_summary.json`:

- does the crop look large enough to cover realistic prior error?
- is the target offset from the prior believable?
- does the crop side length feel too small or too large for your intended navigation uncertainty?

What to check in `pipeline_debug.svg` and `pipeline_summary.json`:

- do the combined outputs look coherent together?
- do the sensitivity cases look reasonable?
- if altitude changes by 10 percent, does the footprint change by about the amount you would expect?
- if heading changes by 10 degrees, does the rotation delta make sense?

## 5. Tell Me Your Review

After you inspect those artifacts, send me a short review in this structure:

```text
Geometry review:
- footprint size looks too small / too large / reasonable
- heading rotation looks wrong / reasonable

Crop review:
- crop size looks too small / too large / reasonable
- prior uncertainty should be about X meters

Sensitivity review:
- looks reasonable / too sensitive / not sensitive enough

Decision:
- keep current assumptions
- adjust assumptions before more code
```

If anything looks wrong, say exactly what seems wrong and by roughly how much.

## 6. Build Your Recorder Around These Formats

You said you will build the actual recorder when you go out and collect data. Build it to emit these formats.

### Replay capture format

Use:

- `configs/replay/dev_packets_v1.jsonl`

Rules:

- the first line should usually be a `session_start` packet
- every later line should be one `frame` packet
- write packets in chronological order
- use JSON-lines, meaning one complete JSON object per line

Important fields for replay:

- `packet_type`
- `schema_version`
- `timestamp_utc`
- `image_name`
- `latitude_deg`
- `longitude_deg`
- `altitude_m`
- `heading_deg`
- `camera_hfov_deg` if not already provided at session level
- `frame_width_px`
- `frame_height_px`
- `prior_latitude_deg` and `prior_longitude_deg` if you have a navigation prior
- `prior_search_radius_m` at session level if uncertainty is roughly stable

### Live packet format

Use:

- `configs/live/dev_live_packet_v1.json`

Rules:

- each live message should be one JSON object
- use `packet_type: "live_frame"`
- keep the rest of the fields aligned with the replay frame format

## 7. What A Good First Real Capture Looks Like

For your first useful data collection session, try to get:

- one short session in a visually distinct area
- a consistent altitude for at least part of the run
- timestamps that match the saved image frames
- accurate latitude and longitude if available
- accurate height above ground if possible
- heading per frame
- horizontal FOV value
- image width and height

If possible, also record:

- whether altitude is really above ground directly under the drone
- whether heading is true yaw, magnetic heading, or another approximation
- how accurate you think the prior position is

## 8. Important Definitions

### AGL

`AGL` means `Above Ground Level`.

That is the drone’s height above the ground directly under the drone.

For this project, that is the preferred meaning of `altitude_m` if your ultrasonic or other sensor supports it.

### Prior

The `prior` is the approximate expected position before localization refinement.

Examples:

- GPS estimate
- dead-reckoning estimate
- previous-frame estimate

If you do not have a prior yet, the current code can still run by falling back to the true frame position for deterministic development, but that is only a placeholder.

## 9. What To Send Me Next

The best next input from you is one of these:

1. A review of the current generated artifacts.
2. A real or semi-real replay capture in the `dev-packet-v1` format.
3. A real or semi-real live packet in the `live_frame` format.

If you send real captured data, also tell me:

- camera model if known
- actual HFOV if known
- whether altitude is AGL
- whether the prior is GPS, dead reckoning, or something else
- what uncertainty in meters you think the prior usually has

## 10. What I Will Do After Your Input

If your review says the current assumptions look good:

- I will harden the live receiver toward a more realistic loop or improve debug overlays

If your review says geometry or crop sizing looks wrong:

- I will adjust the geometry and prior assumptions first

If you provide real data:

- I will adapt the pipeline to your data and move from synthetic inspection to real replay evaluation

## 11. Minimum Checklist Before The Next Field Session

Before you go out to record, confirm all of these:

- you know where image files will be stored
- you know how timestamps will be associated with frames
- you know how latitude and longitude will be recorded
- you know how altitude will be recorded
- you know how heading will be recorded
- you know your frame width and height
- you know where to store the replay `.jsonl` file
- you know whether you have a prior source and what its expected error is

If any item above is unclear, tell me before you build the recorder and I will tighten the format or assumptions first.
