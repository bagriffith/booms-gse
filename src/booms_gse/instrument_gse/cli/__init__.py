import click
from .. import imager as bgse_imag
from .. import spectrometer as bgse_spec


# TODO: Explain what the replay speed actually selects.
def source_options(f):
    return click.option('--replay', '-r', default=False,
                        help="Replay from the entire file.")(
           click.option('--speed', '-x', default=1.0,
                        type=click.FloatRange(min=0, min_open=True),
                        help="When replaying use this speed.")(
           click.option('--serial', '-s', default=False,
                        help="The data target is a serial port.")(f)))


@click.group()
def gse():
    pass


@gse.command()
@click.argument('data_source', type=str)
@source_options
def imager(data_source, **kwargs):
    rate = kwargs['speed'] if kwargs['replay'] else None 
    bgse_imag.run_gse(data_source, rate, live=kwargs['replay'])


@gse.command()
@click.argument('data_source', type=str)
@source_options
@click.option('--save', default=False,
              help="Save the high resolution spectra to pd1.txt and pd2.txt")
def spectrometer(data_source, **kwargs):
    rate = kwargs['speed'] if kwargs['replay'] else None 
    bgse_spec.run_gse(data_source, rate,
                      save=kwargs['save'], live=kwargs['replay'])
