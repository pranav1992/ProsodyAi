class ClassificationServiceError(Exception):
    """The OpenAI classification call failed for a reason that isn't specific
    to the audio file being processed (quota exhausted, bad API key, OpenAI
    outage) -- continuing to transcribe the rest of the batch would just burn
    compute on files guaranteed to fail the same way. `user_message` is
    written for a non-technical dashboard viewer, not a stack trace."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message
