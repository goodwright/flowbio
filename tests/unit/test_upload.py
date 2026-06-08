from flowbio.upload import UploadClient

DEPRECATION_MESSAGE = "Being phased out. Use `flowbio.v2.Client.upload_sample` instead."


def test_upload_sample_remains_marked_deprecated() -> None:
    # The deprecation is carried by typing_extensions.deprecated (a 3.8+
    # backport of warnings.deprecated) so the package imports on Python < 3.13.
    assert getattr(UploadClient.upload_sample, "__deprecated__", None) == DEPRECATION_MESSAGE
