from utilities.choices import ChoiceSet


class MeasurementUnitChoices(ChoiceSet):
    """
    The unit a floor's dimensions are quoted in.

    Coordinates are always stored in centimetres. This governs how a dimension is entered and
    displayed, so an operator working in feet is not made to convert by hand.
    """

    METRES = 'm'
    FEET = 'ft'

    CHOICES = (
        (METRES, 'Metres'),
        (FEET, 'Feet'),
    )
