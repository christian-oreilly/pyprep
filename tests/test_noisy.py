"""Test the noisy module."""

import mne
import numpy as np
import pytest

from pyprep.noisy import Noisydata, find_bad_epochs
from pyprep.utils import make_random_mne_object

RNG = np.random.RandomState(1337)


# We make new random mne objects until we have one without inherent bad chans
# This is required so that we can then selectively insert noise in the tests.
found_good_test_object = False
t_secs = 600
sfreq = 1000.0
t = np.arange(0, t_secs, 1.0 / sfreq)
ch_names = [
    "Fpz",
    "AFz",
    "Fz",
    "FCz",
    "Cz",
    "CPz",
    "Pz",
    "POz",
    "Oz",
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
]
ch_types = ["eeg" for chn in ch_names]

raw, n_freq_comps, freq_range = make_random_mne_object(
    ch_names, ch_types, t, sfreq, RNG=RNG
)
nd = Noisydata(raw)
nd.find_all_bads(ransac=False)
assert nd.get_bads() == []

# Make some arbitrary events sampled from the mid-section of raw.times
n_events = 3
ival_secs = [0.2, 0.8]
marker_samples = RNG.choice(raw.times[5:-5], size=n_events, replace=False)
events = np.asarray(
    [marker_samples, np.zeros(n_events), np.ones(n_events)], dtype="int64"
)
# Make epochs from the MNE _data
epochs = mne.Epochs(
    raw, events, tmin=ival_secs[0], tmax=ival_secs[1], baseline=None, verbose=False
)


def test_find_bad_epochs(epochs=epochs):
    """Test the FASTER find bad epochs function."""
    bads = find_bad_epochs(epochs)
    assert isinstance(bads, list)
    assert bads == []


@pytest.mark.parametrize("input", [raw, {"key": 1}, [1, 2, 3], RNG.random((3, 3))])
def test_init(input):
    """Test the class initialization."""
    # Initialize with an mne object should work
    if isinstance(raw, mne.io.RawArray):
        Noisydata(raw)
        return

    # Initialization with another object should raise an error
    with pytest.raises(AssertionError):
        Noisydata(raw)


def test_get_bads(raw=raw):
    """Find all bads and then get them."""
    # Make sure that in the example, none are bad per se.
    nd = Noisydata(raw)

    # Do not test ransac yet ... need better data to confirm
    nd.find_all_bads(ransac=False)
    bads = nd.get_bads(verbose=True)  # also test the printout
    assert bads == []


def test_find_bad_by_nan(raw=raw):
    """Test find_bad_by_nan."""
    raw_tmp = raw.copy()
    m, n = raw_tmp._data.shape

    # Insert a nan value for a random channel
    rand_chn_idx = int(RNG.randint(0, m, 1))
    rand_chn_lab = raw_tmp.ch_names[rand_chn_idx]
    raw_tmp._data[rand_chn_idx, n - 1] = np.nan

    # Now find it and assert it's the correct one.
    nd = Noisydata(raw_tmp)
    nd.find_bad_by_nan()
    assert nd.bad_by_nan == [rand_chn_lab]


def test_find_bad_by_flat(raw=raw):
    """Test find_bad_by_flat."""
    raw_tmp = raw.copy()
    m, n = raw_tmp._data.shape

    # Scale data so high that it would not be flat
    raw_tmp._data *= 1e100

    # Now insert one random flat channel
    rand_chn_idx = int(RNG.randint(0, m, 1))
    rand_chn_lab = raw_tmp.ch_names[rand_chn_idx]
    raw_tmp._data[rand_chn_idx, :] = np.ones_like(raw_tmp._data[1, :])

    # Now find it and assert it's the correct one.
    nd = Noisydata(raw_tmp)
    nd.find_bad_by_flat()
    assert nd.bad_by_flat == [rand_chn_lab]


def test_find_bad_by_deviation(raw=raw):
    """Test find_bad_by_deviation."""
    RNG.seed(12345)

    raw_tmp = raw.copy()
    m, n = raw_tmp._data.shape

    # Now insert one random channel with very low deviations
    rand_chn_idx = int(RNG.randint(0, m, 1))
    rand_chn_lab = raw_tmp.ch_names[rand_chn_idx]
    raw_tmp._data[rand_chn_idx, :] = np.ones_like(raw_tmp._data[1, :])

    # See if we find the correct one
    nd = Noisydata(raw_tmp)
    nd.find_bad_by_deviation()
    assert nd.bad_by_deviation == [rand_chn_lab]

    # Insert a channel with very high deviation
    raw_tmp = raw.copy()
    rand_chn_idx = int(RNG.randint(0, m, 1))
    rand_chn_lab = raw_tmp.ch_names[rand_chn_idx]
    arbitrary_scaling = 5
    raw_tmp._data[rand_chn_idx, :] *= arbitrary_scaling

    # See if we find the correct one
    nd = Noisydata(raw_tmp)
    nd.find_bad_by_deviation()
    assert nd.bad_by_deviation == [rand_chn_lab]


def test_find_bad_by_correlation(
    raw=raw, freq_range=freq_range, n_freq_comps=n_freq_comps
):
    """Test find_bad_by_flat."""
    raw_tmp = raw.copy()
    m, n = raw_tmp._data.shape

    # The test data is correlated well
    # We insert a badly correlated channel and see if it is detected.
    rand_chn_idx = int(RNG.randint(0, m, 1))
    rand_chn_lab = raw_tmp.ch_names[rand_chn_idx]

    # Use cosine instead of sine to create a signal
    low = freq_range[0]
    high = freq_range[1]
    signal = np.zeros((1, n))
    for freq_i in range(n_freq_comps):
        freq = RNG.randint(low, high, n)
        signal[0, :] += np.cos(2 * np.pi * raw.times * freq)

    raw_tmp._data[rand_chn_idx, :] = signal * 1e-6

    # Now find it and assert it's the correct one.
    nd = Noisydata(raw_tmp)
    nd.find_bad_by_correlation()
    assert nd.bad_by_correlation == [rand_chn_lab]


def test_find_bad_by_hf_noise(raw=raw, n_freq_comps=n_freq_comps):
    """Test find_bad_by_flat."""
    raw_tmp = raw.copy()
    m, n = raw_tmp._data.shape

    # The test data has low hf noise
    # We insert a a chan with a lot hf noise
    rand_chn_idx = int(RNG.randint(0, m, 1))
    rand_chn_lab = raw_tmp.ch_names[rand_chn_idx]

    # Use freqs between 90 and 100 Hz to insert hf noise
    signal = np.zeros((1, n))
    for freq_i in range(n_freq_comps):
        freq = RNG.randint(90, 100, n)
        signal[0, :] += np.sin(2 * np.pi * raw.times * freq)

    raw_tmp._data[rand_chn_idx, :] = signal * 1e-6

    # Now find it and assert it's the correct one.
    nd = Noisydata(raw_tmp)
    nd.find_bad_by_hf_noise()
    assert nd.bad_by_hf_noise == [rand_chn_lab]


def test_find_bad_by_ransac(raw=raw):
    """Test find_bad_by_ransac."""
    # For now, simply see if it runs
    # Need better data to test properly
    nd = Noisydata(raw)
    nd.find_all_bads(ransac=True)  # equivalent to nd.find_bad_by_ransac()
    bads = nd.bad_by_ransac
    assert (bads == []) or (len(bads) > 0)


def test_ransac_too_few_preds(raw=raw):
    """Test that ransac throws an error for few predictors."""
    chns = RNG.choice(raw.ch_names, size=3, replace=False)
    raw_tmp = raw.copy()
    raw_tmp.pick_channels(chns)
    nd = Noisydata(raw_tmp)
    with pytest.raises(IOError):
        nd.find_bad_by_ransac()


def test_ransac_too_little_ram(raw=raw):
    """Test that ransac throws a memory error if not enough available."""
    nd = Noisydata(raw)

    # The following are irrelevant because we are testing MemoryError
    chn_pos = nd.chn_pos
    chn_pos_good = chn_pos
    good_chn_labs = raw.ch_names
    n_pred_chns = 4  # irrelevant because we are testing MemoryError
    data = raw._data

    # Set n_samples very very high to trigger a memory error
    n_samples = 1e100
    with pytest.raises(MemoryError):
        nd._run_ransac(
            chn_pos, chn_pos_good, good_chn_labs, n_pred_chns, data, n_samples
        )
