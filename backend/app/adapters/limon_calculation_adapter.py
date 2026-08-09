"""Import and orchestrate existing production LiMon Python stage functions here."""


class LimonCalculationAdapter:
    def recalculate(self, row, stages):
        raise NotImplementedError("Wire to production LiMon calculations.")
