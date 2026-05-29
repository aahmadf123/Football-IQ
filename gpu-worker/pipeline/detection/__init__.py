"""Detection adapters: SAHI slicing, dual-resolution merge, dedicated ball
detection, and official suppression (Issues #128 / #133 / #148).

All adapters wrap a router-resolved :class:`~pipeline.detector_models.DetectorBase`;
none instantiate YOLO/SAM directly, so same-session safety is inherited from
whatever the model router selected.
"""
