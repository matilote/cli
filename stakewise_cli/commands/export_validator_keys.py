from os import getcwd, mkdir
from os.path import exists, join
from typing import Dict

import click
from eth_typing import HexStr
from py_ecc.bls import G2ProofOfPossession
from web3 import Web3

from stakewise_cli.committee_shares import rsa_encrypt
from stakewise_cli.eth1 import is_validator_registered
from stakewise_cli.eth2 import get_mnemonic_signing_key, validate_mnemonic
from stakewise_cli.networks import AVAILABLE_NETWORKS, MAINNET
from stakewise_cli.queries import get_ethereum_gql_client
from stakewise_cli.settings import IS_LEGACY
from stakewise_cli.typings import SigningKey


@click.command(help="Export registered private keys from the mnemonic")
@click.option(
    "--network",
    default=MAINNET,
    help="The network of ETH2 you are targeting.",
    prompt="Please choose the network name",
    type=click.Choice(
        AVAILABLE_NETWORKS,
        case_sensitive=False,
    ),
)
@click.option(
    "--output-dir",
    default=join(getcwd(), "exported_keys"),
    help="The folder where private keys will be saved.",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
)
@click.option(
    "--encode-public-key",
    help="The RSA public key file to encode exported keys.",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
def export_validator_keys(
    network: str, output_dir: str, encode_public_key: str
) -> None:
    mnemonic = click.prompt(
        'Enter your mnemonic separated by spaces (" ")',
        value_proc=validate_mnemonic,
        type=click.STRING,
    )

    with open(encode_public_key, "r") as f:
        recipient_public_key = f.read()

    eth_gql_client = get_ethereum_gql_client(network)

    click.secho(
        "Processing registered validators... .\n",
        fg="green",
    )
    keypairs: Dict[HexStr, SigningKey] = {}
    index = 0
    while True:
        signing_key = get_mnemonic_signing_key(mnemonic, index, IS_LEGACY)
        public_key = Web3.toHex(G2ProofOfPossession.SkToPk(signing_key.key))

        is_registered = is_validator_registered(
            gql_client=eth_gql_client, public_key=public_key
        )
        if is_registered:
            keypairs[public_key] = signing_key
            index += 1
            continue
        break

    if not keypairs:
        raise click.ClickException("No registered validators private keys")

    if not exists(output_dir):
        mkdir(output_dir)
    with click.progressbar(
        length=len(keypairs),
        label="Saving encoded private keys\t\t",
        show_percent=False,
        show_pos=True,
    ) as bar:
        for public_key, signing_key in keypairs.items():
            secret = str(signing_key.key)
            enc_session_key, nonce, tag, ciphertext = rsa_encrypt(
                recipient_public_key=recipient_public_key,
                data=secret,
            )
            with open(join(output_dir, f"{public_key}.enc"), "wb") as f:
                for data in (enc_session_key, nonce, tag, ciphertext):
                    f.write(data)
            bar.update(1)

    click.secho(
        f"Exported {len(keypairs)} encrypted private keys to {output_dir} folder.\n",
        bold=True,
        fg="green",
    )
