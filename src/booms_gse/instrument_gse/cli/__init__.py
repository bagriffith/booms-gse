import click

from .. import imager as bgse_imag
from .. import spectrometer as bgse_spec


# TODO: Explain what the replay speed actually selects.
def source_options(f):
    return click.option('--replay', '-r', default=False, is_flag=True,
                        help="Replay from the entire file.")(
           click.option('--speed', '-x', default=1.0,
                        type=click.FloatRange(min=0, min_open=True),
                        help="When replaying use this speed.")(
           click.option('--serial', '-s', default=False, is_flag=True,
                        help="The data target is a serial port.")(f)))


@click.group()
def gse():
    pass


@gse.command()
@click.argument('data_source', type=str)
@source_options
def imager(data_source, **kwargs):
    if kwargs['serial']:
        rate = None
    else:
        rate = kwargs['speed'] if kwargs['replay'] else 999_999_999.
    bgse_imag.run_gse(data_source, rate, live=not kwargs['replay'])


@gse.command()
@click.argument('data_source', type=str)
@source_options
@click.option('--save', default=False,
              help="Save the high resolution spectra to pd1.txt and pd2.txt")
def spectrometer(data_source, **kwargs):
    if kwargs['serial']:
        rate = None
    else:
        rate = kwargs['speed'] if kwargs['replay'] else 999_999_999.
    bgse_spec.run_gse(data_source, rate,
                      save=kwargs['save'], live=not kwargs['replay'])


if __name__ == '__main__':
    gse()
