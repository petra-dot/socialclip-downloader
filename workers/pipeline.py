def plan_postprocess(output_type, convert, source_height, target_resolution):
    """Decide what to do after a download.

    Returns one of: "audio" (extract MP3), "convert", "skip_low",
    "skip_equal", "keep".
    """
    if output_type == "MP3":
        return "audio"
    if not convert:
        return "keep"
    if source_height and target_resolution > source_height:
        return "skip_low"
    if source_height and target_resolution == source_height:
        return "skip_equal"
    return "convert"
