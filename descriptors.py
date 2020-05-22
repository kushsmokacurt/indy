#!/usr/bin/env python3
from __future__ import annotations

from typing import List, Optional, Tuple

from bip32 import BIP32, HARDENED_INDEX

from scripts import ScriptType

# m: master key
# a: account index
# i: address index
descriptors = {
    "m/44'/0'/a'/0/i": [ScriptType.LEGACY],  # BIP44, external
    "m/44'/0'/a'/1/i": [ScriptType.LEGACY],  # BIP44, change
    "m/49'/0'/a'/0/i": [ScriptType.COMPAT],  # BIP49, external
    "m/49'/0'/a'/1/i": [ScriptType.COMPAT],  # BIP49, change
    "m/84'/0'/a'/0/i": [ScriptType.SEGWIT],  # BIP84, external
    "m/84'/0'/a'/1/i": [ScriptType.SEGWIT],  # BIP84, change
    "m/0'/0'/i'": [ScriptType.LEGACY, ScriptType.COMPAT, ScriptType.SEGWIT],  # Bitcoin Core
    "m/0'/0/i": [ScriptType.LEGACY, ScriptType.COMPAT, ScriptType.SEGWIT],  # BRD/Hodl/Coin/Multibit external
    "m/0'/1/i": [ScriptType.LEGACY, ScriptType.COMPAT, ScriptType.SEGWIT],  # BRD/Hodl/Coin/Multibit change
    "m/44'/0'/2147483647'/0/i": [ScriptType.LEGACY],  # Samourai ricochet, BIP44, external
    "m/44'/0'/2147483647'/1/i": [ScriptType.LEGACY],  # Samourai ricochet, BIP44, change
    "m/49'/0'/2147483647'/0/i": [ScriptType.COMPAT],  # Samourai ricochet, BIP49, external
    "m/49'/0'/2147483647'/1/i": [ScriptType.COMPAT],  # Samourai ricochet, BIP49, change
    "m/84'/0'/2147483647'/0/i": [ScriptType.SEGWIT],  # Samourai ricochet, BIP84, external
    "m/84'/0'/2147483647'/1/i": [ScriptType.SEGWIT],  # Samourai ricochet, BIP84, change
    "m/84'/0'/2147483646'/0/i": [ScriptType.SEGWIT],  # Samourai post-mix, external
    "m/84'/0'/2147483646'/1/i": [ScriptType.SEGWIT],  # Samourai post-mix, change
    "m/84'/0'/2147483645'/0/i": [ScriptType.SEGWIT],  # Samourai pre-mix, external
    "m/84'/0'/2147483645'/1/i": [ScriptType.SEGWIT],  # Samourai pre-mix, change
    "m/84'/0'/2147483644'/0/i": [ScriptType.SEGWIT],  # Samourai bad-bank, external
    "m/84'/0'/2147483644'/1/i": [ScriptType.SEGWIT],  # Samourai bad-bank, change
}


class Path:
    """
    Derivation path from a master key that may have a variable account number, and a variable index number.
    """

    def __init__(self, path: str):
        self.path = path

    def has_variable_account(self) -> bool:
        """
        Whether this path has the account level as a free variable.
        """
        return self.path.find('a') >= 0

    def has_variable_index(self) -> bool:
        """
        Whether this path has the index level as a free variable.
        """
        return self.path.find('i') >= 0

    def to_list(self, index: int = None, account: int = None) -> List[int]:
        """
        Transform this path into a list of valid derivation indexes.
        """
        # replace the placeholders
        path = self.path.replace('a', str(account)).replace('i', str(index))
        parts = path.split('/')[1:]

        # compute the derivation indexes
        indexes = []
        for part in parts:
            if part.endswith("'"):
                indexes.append(HARDENED_INDEX + int(part[:-1]))
            else:
                indexes.append(int(part))
        return indexes

    def with_account(self, account: int) -> Path:
        """
        Get a new path with a fixed account.
        """
        return Path(self.path.replace('a', str(account)))

    def with_index(self, index: int) -> Path:
        """
        Get a new path with a fixed index.
        """
        return Path(self.path.replace('i', str(index)))

    def __eq__(self, other):
        if isinstance(other, Path):
            return self.path == other.path
        return NotImplemented

    def __hash__(self):
        return hash(self.path)


class DescriptorScriptIterator:
    """
    Iterator that can traverse the all the possible scripts generated by a descriptor (ie. a path and script type pair).
    """

    def __init__(self, path: Path, script_type: ScriptType, max_index: int, max_account: int):
        self.path = path
        self.script_type = script_type
        self.index = 0
        self.account = 0
        self.max_index = max_index if path.has_variable_index() else 0
        self.max_account = max_account if path.has_variable_account() else 0
        self.total_scripts = (self.max_index + 1) * (self.max_account + 1)

    def next_script(self, master_key: BIP32) -> Optional[Tuple[bytes, Path, ScriptType]]:
        """
        Fetch the next script for the current descriptor.
        """
        if self.index > self.max_index or self.account > self.max_account:
            return None

        # derive the next script
        path = self.path.with_account(self.account)
        pubkey = master_key.get_pubkey_from_path(path.to_list(self.index))
        script = self.script_type.build_output_script(pubkey)

        # Since traversing the entire [0; MAX_INDEX] x [0; MAX_ACCOUNT] space of combinations might take a while, we
        # walk the (index, account) grid in diagonal order. This order prioritizes the most probable combinations
        # (ie. low index, low account), while letting us explore a large space in the long run.
        #
        #           0     1     2
        #         ↙     ↙     ↙
        #    (0,0) (1,0) (2,0)  3
        #   ↙     ↙     ↙     ↙
        #    (0,1) (1,1) (2,1)  4
        #   ↙     ↙     ↙     ↙
        #    (0,2) (1,2) (2,2)  5
        #   ↙     ↙     ↙     ↙
        #    (0,3) (1,3) (2,3)
        #   ↙     ↙     ↙

        if self.index == 0 or self.account == self.max_account:
            # if we reached the border, start in the next diagonal
            diagonal_total = self.index + self.account + 1
            self.index = min(diagonal_total, self.max_index)
            self.account = diagonal_total - self.index
        else:
            # go down the diagonal
            self.index -= 1
            self.account += 1

        return script, path, self.script_type


class ScriptIterator:
    """
    Iterator that can traverse all the possible scripts of all the possible descriptors.
    """

    def __init__(self, master_key: BIP32, max_index: int, max_account: int):
        self.master_key = master_key
        self.index = 0
        self.descriptors = []
        for path, types in descriptors.items():
            for type in types:
                self.descriptors.append(DescriptorScriptIterator(Path(path), type, max_index, max_account))
        self.total_scripts = sum([d.total_scripts for d in self.descriptors])

    def _next_descriptor_script(self) -> Optional[Tuple[bytes, Path, ScriptType]]:
        """
        Fetch the next script from the next descriptor. If the descriptor doesn't have a next script, remove it.
        """
        descriptor = self.descriptors[self.index]
        iter = descriptor.next_script(self.master_key)

        if iter is None:
            del self.descriptors[self.index]
            self.index -= 1

        self.index += 1
        if self.index >= len(self.descriptors):
            self.index = 0

        return iter

    def next_script(self) -> Optional[Tuple[bytes, Path, ScriptType]]:
        """
        Fetch the next script, cycling the descriptors in order to explore all of them progressively.
        """
        while len(self.descriptors) > 0:
            iter = self._next_descriptor_script()
            if iter is not None:
                return iter

        return None