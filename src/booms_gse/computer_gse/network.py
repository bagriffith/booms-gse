"""Tools to process UDP packets from the flight computer.

Generally this can be used by just calling the asynchronous function
`asyncio.run(receive_packets(ip, port, processors))` with a tuple of
processors, each instances of `PacketProcessor` or one of its subclasses.
"""
import asyncio
import logging
import os
import pty
from itertools import chain
from pathlib import Path

import serial
from bokeh.application import Application
from bokeh.application.handlers import ScriptHandler
from bokeh.server.server import Server

BOOMS_SERIAL_DIR = Path(
    os.environ.get('BOOMS_SERIAL_DIR', default='/dev/booms'))

PLAYBACK_PATH = Path(os.environ.get('BOOMS_PLAYBACK', default='playback'))
COMMAND_PACKET = b'\x90\xeb\xe3\x56\xa0\xa1\x00\x04\xc0\xa8\x02\x01'
COMPUTER_IP = '192.168.2.101'
COMMAND_PORT = 50501

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def write_with_lock(file, data, lock):
    """Acquire an async lock before writting and flushing data.

    Args:
        file: A file like object that has a method write(data).
        data (bytes): A bytes object to be written.
        lock (asyncio.Lock): Lock to prevent simultaneous writes.
    """
    async with lock:
        file.write(data)
        file.flush()


class FlightComputerReceiver(asyncio.DatagramProtocol):
    """Endpoint for flight computer UDP packets that runs a set of processors
    on each packet received."""
    def __init__(self, processors=None):
        """Initialize the instance with a set of processors.

        Args:
            processors (tuple(PacketProcessor)): Each processor should will
                have received() called for each UDP packet.
        """
        if processors is None:
            processors = tuple()
        self.processors = tuple(processors)
        self.transport = None

    def connection_made(self, transport):
        """Setup the prcessors when a connection is made."""
        self.transport = transport

        for p in self.processors:
            p.setup(transport)

    def connection_lost(self, exc):
        """Close the processors when the connection is lost."""
        logger.info('Lost UDP connection')
        if exc is not None:
            logger.warning('UDP closed with exception.', exc_info=exc)

        for p in self.processors:
            p.close()

    def datagram_received(self, data, addr):
        """Run the processors for each packet received."""
        logger.debug('Datagram received from %s', addr)

        for p in self.processors:
            p.receive(data)

    def error_received(self, exc):
        """Log any errors that occur."""
        logger.warning('Flight Computer UDP error received', exc_info=exc)


class PacketProcessor:
    """Contain an operation to be run on packets as they're received."""
    def __init__(self):
        self.transport = None

    def setup(self, transport):
        """Initialize anything needed for packet processing.

        Args:
            transport (DatagramTransport): The transport packets are coming in
                on. It is saved for optional use in processing.
        """
        self.transport = transport

    def receive(self, packet):
        """The function run on each packet.

        Args:
        packet (bytes): The entire UDP packet received. Should be overloaded by
            subclasses.
        """

    def close(self):
        """Clear the transport variable. Should be overloaded with cleanup
        when needed by a subclass.
        """
        # Leave closing transport to the DatagramProtocol instance
        self.transport = None


class PacketSerial(PacketProcessor):
    """Forward the contents of the frame for a selected imager or spectrometer
    to a serial port."""
    SERIAL_CONFIGS = {'imag': {'baudrate': 230400},
                      'spec': {'baudrate': 38400}}

    def __init__(self, device_id, serial_port):
        """Initialize the serial packet processor

        Args:
            device_id (int): The device ID set in the flight software. It
                should be one byte (0 <= device_id < 256). Imagers will start
                with the first four bits following the pattern 0xC* and
                spectrometers 0xD*.
        """
        super().__init__()

        self.serial_lock = asyncio.Lock()
        self.device_id = int(device_id)
        self.serial_port = serial_port
        self.serial = None

    def setup(self, transport):
        """Setup the serial port target for packets."""
        # Serial config should match the instrument type. Follow the pattern
        #     set by the first four bits.
        if (self.device_id & 0xF0) == 0xC0:
            serial_kwargs = self.SERIAL_CONFIGS['imag']
        elif (self.device_id & 0xF0) == 0xD0:
            serial_kwargs = self.SERIAL_CONFIGS['spec']
        else:
            # Other devices are not supported yet.
            raise RuntimeError(f'Byte id {self.device_id} is not a supported '
                               'device. Must be imager (0xC*) or spectrometer '
                               '(0xD*).')

        self.serial = serial.Serial(port=self.serial_port, **serial_kwargs)

        if self.serial is None:
            # Triggered if there was an error setting up the serial connection.
            raise RuntimeError('Serial not initialized.')

    def receive(self, packet):
        """Write the packet to the serial port."""
        if len(packet) < 16:
            logger.warning('Packet is too short for header (<16 bytes).')

        if packet[4] == self.device_id:
            if self.serial is None:
                # Triggered if self.setup() was skipped or self.close()
                #    has been called.
                raise RuntimeError('Serial not initialized.')

            asyncio.create_task(
                write_with_lock(self.serial, packet[16:], self.serial_lock)
            )

    def close(self):
        """Close the serial connection."""
        if self.serial is not None:
            self.serial.close()
        super().close()


class PacketForwarder(PacketProcessor):
    """Forward all UPD packets to a new IP and port."""
    def __init__(self, target_ip, target_port):
        """Initialize to forward UDP packets to the set IP and port.

        Args:
            target_ip (ip_address): Valid IPv4 or IPv6 address to receive
                the packets.
            target_port (int): Valid UDP port, 0 < target_port <= 65535)
        """
        super().__init__()

        self.target_ip = target_ip
        self.target_port = target_port

    def receive(self, packet):
        """Forward the packet to the configured IP and port"""
        self.transport.sendto(packet, (self.target_ip, self.target_port))


class PacketLogger(PacketProcessor):
    """Write the packet contents for each imager and spectrometer to files."""
    IMAG_IDS = set([0xC0 + i for i in range(7)])
    SPEC_IDS = set([0xD0 + i for i in range(3)])

    def __init__(self, path_root=None, path_dict=None, fd_dict=None):
        """Initialize the file writter.

        Args:
            path_root (Path): Parent directory to contain imager and
                spectrometer log files. If it doesn't exist, it will be
                created.
            path_dict (dict): Dictionary with keys of instrument IDs as int
                matched to a path where that instrument's data will be
                recorded. If the file doesn't exist, it will be created.
            fd_dict (dict): Dictionary with keys of instrument IDs as int
                matched to a file descriptor where that instrument's data
                will be recorded.
        """
        super().__init__()

        if path_root is not None:
            # Set the paths for each instrument in the path_root directory
            Path(path_root).mkdir(exist_ok=True)
            if path_dict is not None:
                raise ValueError('Only one output file option may be selected')

            path_dict = dict()
            # Imagers:
            for spec_id in self.SPEC_IDS:
                path_dict[spec_id] = \
                    Path(path_root) / f'spec_{spec_id & 0x0F:}.dat'
            # Spectrometers:
            for imag_id in self.IMAG_IDS:
                path_dict[imag_id] = \
                    Path(path_root) / f'imag_{imag_id & 0x0F:}.dat'
        logger.debug('Paths: %s', path_dict)

        if path_dict is not None:
            # Get file descriptors for each instrument log path.
            if fd_dict is not None:
                raise ValueError('Only one output file option may be selected')
            fd_dict = dict()
            for device_id, path in path_dict.items():
                logger.debug('Creating %s', hex(device_id))
                # Get the fd
                fd_dict[device_id] = \
                    os.open(path, os.O_CREAT | os.O_WRONLY | os.O_NONBLOCK)

        # Make sure only imagers and spectrometer ids are provided. Not all
        # are needed, but no other id may be added.
        if set(fd_dict.keys()) > self.SPEC_IDS.union(self.IMAG_IDS):
            raise ValueError('Invalid device id provided.')
        self.fds = fd_dict.copy()
        self.f_lock = asyncio.Lock()
        logger.debug('File Descriptors: %s', self.fds)
        # Dictionary to hold file objects once opened with self.setup()
        self.open_files = {k: None for k in self.fds.keys()}

    def setup(self, transport):
        """Open all of the instrument log files."""
        super().setup(transport)

        self.open_files.update(
            {device_id: os.fdopen(fd, "wb")
             for device_id, fd in self.fds.items()})

    def close(self):
        """Close all of the open instrument log files."""
        for device_id, file in self.open_files.items():
            if file is not None:
                file.close()
            self.open_files[device_id] = None

    def receive(self, packet):
        """Write the packet to it's appropriate instrument log file."""
        if len(packet) < 16:
            logger.warning('Packet is too short for header (<16 bytes).')

        id_byte = packet[4]
        logger.debug('ID Byte: %s', hex(id_byte))

        if (file := self.open_files.get(id_byte, None)):
            asyncio.create_task(
                write_with_lock(file, packet[16:], self.f_lock))
        else:
            pass
            # logger.warning('File for %s is closed', hex(id_byte))


class PacketPseudoSerial(PacketLogger):
    """Process instruments with log file recorder, but the log files are
        connected to a pseudo serial port."""
    def __init__(self):
        """Initialize the processor and pick the pseudo serial ports."""
        self.serial = dict()

        fd_dict = dict()
        for device_id in chain(self.IMAG_IDS, self.SPEC_IDS):
            primary_fd, secondary_df = pty.openpty()
            fd_dict[device_id] = primary_fd
            self.serial[device_id] = Path(os.ttyname(secondary_df))

        super().__init__(fd_dict=fd_dict)


class MMGSEPacket(PacketForwarder):
    """Process the packets by forwarding them to a loopback address, and start
    an mm_gse bokeh server listening to that port."""
    def __init__(self):
        """Initialize the processor and set up a forwarding processor to
            the mm_gse server."""
        super().__init__('127.0.0.1', 20502)
        self.server = None

    def setup(self, transport):
        """Start the packer forwarder and start the bokeh server for mm_gse."""
        super().setup(transport)

        mm_gse_path = Path(__file__).parent.parent / 'mm_gse.py'
        print(mm_gse_path)
        apps = {'/': Application(ScriptHandler(filename=mm_gse_path))}
        self.server = Server(apps)
        self.server.start()
        url = f"http://localhost:{self.server.port}{self.server.prefix}/"
        print(f"Bokeh app running at: {url}")

    def close(self):
        """Close the packet forwarder and the bokeh server."""
        super().close()
        self.server.stop()


async def receive_packets(ip_addr, port, processors=None,
                          from_file=None, speed=1.0):
    """Start an async loop to receive all incoming UDP packers and run
        the processors provided on each of them."""
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    def create_endpoint(processors=processors):
        return FlightComputerReceiver(processors)

    transport, _ = await loop.create_datagram_endpoint(create_endpoint,
                                                       local_addr=(ip_addr,
                                                                   port))

    try:
        if from_file is not None:
            await start_playback(from_file, speed=speed, port=port)
            await asyncio.sleep(1.0)  # Wait for buffers to process.
        else:
            await on_con_lost
    except asyncio.exceptions.CancelledError:
        logger.debug('Cancelled', stack_info=True, exc_info=True)
    finally:
        transport.close()


async def start_playback(file, **kwargs):
    """Start an asyncio thread calling the middleman playback binary to
        replay a flight computer data file."""
    if not PLAYBACK_PATH.exists():
        raise RuntimeError('Could not find playback executable. '
                           'Set env variable BOOMS_PLAYBACK.')
    command = [str(PLAYBACK_PATH.absolute()), str(file.absolute())]

    # Options
    option_flags = {'address': '-i',
                    'port': '-p',
                    'system_id': '-fs',
                    'tm_type': '-ft',
                    'speed': '-s'}

    for option, flag in option_flags.items():
        if option in kwargs:
            command.extend([flag, str(kwargs[option])])

    command = [x.replace(' ', r'\ ') for x in command]
    command = ' '.join(command)
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()
    logger.warning(stderr.decode())
    logger.debug(stdout.decode())
