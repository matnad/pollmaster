"""Exception Classes for the Poll Wizard"""


class StopWizard(RuntimeError):
    pass


class InputError(RuntimeError):
    pass


class InvalidInput(InputError):
    pass


class ReservedInput(InputError):
    pass


class DuplicateInput(InputError):
    pass


class WrongNumberOfArguments(InputError):
    pass


class ExpectedInteger(InputError):
    pass


class ExpectedSeparator(InputError):
    def __init__(self, separator):
        self.separator = separator


class OutOfRange(InputError):
    pass


class DateOutOfRange(InputError):
    def __init__(self, date):
        self.date = date


class InvalidRoles(InputError):
    def __init__(self, roles):
        self.roles = roles
