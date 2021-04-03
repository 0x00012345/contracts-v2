import json

from brownie import nTransparentUpgradeableProxy
from brownie.network import web3

ARTIFACTS = [
    "CashMarket",
    "Directory",
    "ERC1155Token",
    "ERC1155Trade",
    "Escrow",
    "Liquidation",
    "Portfolios",
    "RiskFramework",
    "WETH",
    "ERC1820Registry",
]


def load_artifacts():
    artifacts = {}
    for name in ARTIFACTS:
        with open("./scripts/v1artifacts/" + name + ".json", "r") as f:
            data = json.load(f)
            artifacts[name] = data

    return artifacts


def deploy_proxied_contract(name, artifacts, deployer, proxyAdmin, contracts, constructor_args=[]):
    impl = deploy_contract(name, artifacts, deployer, contracts)

    initializeData = impl.encodeABI(fn_name="initialize", args=constructor_args)
    proxy = nTransparentUpgradeableProxy.deploy(
        impl.address, proxyAdmin.address, initializeData, {"from": deployer}
    )

    print("Deployed proxy for %s to %s" % (name, str(proxy.address)))

    return web3.eth.contract(abi=impl.abi, address=proxy.address)


def deploy_contract(name, artifacts, deployer, contracts=None):
    bytecode = artifacts[name]["bytecode"]
    if len(artifacts[name]["linkReferences"]) > 0:
        for (k, lib) in artifacts[name]["linkReferences"].items():
            address = None
            key = list(lib.keys())[0]
            if key == "Liquidation":
                address = contracts["Liquidation"].address
            else:
                address = contracts["RiskFramework"].address

            for offset in lib[key]:
                byteOffsetStart = offset["start"] * 2 + 2
                byteOffsetEnd = byteOffsetStart + offset["length"] * 2
                bytecode = bytecode[0:byteOffsetStart] + address[2:] + bytecode[byteOffsetEnd:]
    contract = web3.eth.contract(abi=artifacts[name]["abi"], bytecode=bytecode)

    tx_hash = contract.constructor().transact({"from": deployer.address})
    tx_receipt = web3.eth.waitForTransactionReceipt(tx_hash)

    print("%s deployed to %s" % (name, str(tx_receipt.contractAddress)))

    return web3.eth.contract(abi=contract.abi, address=tx_receipt.contractAddress)


def deploy_v1(v2env):
    artifacts = load_artifacts()
    contracts = {}
    deployer = v2env.deployer
    proxyAdmin = v2env.proxyAdmin

    contracts["ERC1820Registry"] = deploy_contract("ERC1820Registry", artifacts, deployer)
    contracts["WETH"] = deploy_contract("WETH", artifacts, deployer)
    contracts["Liquidation"] = deploy_contract("Liquidation", artifacts, deployer)
    contracts["RiskFramework"] = deploy_contract("RiskFramework", artifacts, deployer)
    contracts["CashMarket"] = deploy_contract("CashMarket", artifacts, deployer)

    contracts["Directory"] = deploy_proxied_contract(
        "Directory", artifacts, deployer, proxyAdmin, contracts, [deployer.address]
    )

    contracts["Escrow"] = deploy_proxied_contract(
        "Escrow",
        artifacts,
        deployer,
        proxyAdmin,
        contracts,
        [
            contracts["Directory"].address,
            deployer.address,
            contracts["ERC1820Registry"].address,
            contracts["WETH"].address,
        ],
    )
    contracts["Portfolios"] = deploy_proxied_contract(
        "Portfolios",
        artifacts,
        deployer,
        proxyAdmin,
        contracts,
        [contracts["Directory"].address, deployer.address, 1, 8],
    )
    contracts["ERC1155Token"] = deploy_proxied_contract(
        "ERC1155Token",
        artifacts,
        deployer,
        proxyAdmin,
        contracts,
        [contracts["Directory"].address, deployer.address],
    )
    contracts["ERC1155Trade"] = deploy_proxied_contract(
        "ERC1155Trade",
        artifacts,
        deployer,
        proxyAdmin,
        contracts,
        [contracts["Directory"].address, deployer.address],
    )

    contracts["Directory"].functions.setContract(0, contracts["Escrow"].address).transact(
        {"from": deployer.address}
    )
    contracts["Directory"].functions.setContract(1, contracts["Portfolios"].address).transact(
        {"from": deployer.address}
    )
    contracts["Directory"].functions.setContract(2, contracts["ERC1155Token"].address).transact(
        {"from": deployer.address}
    )
    contracts["Directory"].functions.setContract(3, contracts["ERC1155Trade"].address).transact(
        {"from": deployer.address}
    )

    contracts["Directory"].functions.setDependencies(0, [1, 3]).transact({"from": deployer.address})
    contracts["Directory"].functions.setDependencies(1, [0, 2, 3]).transact(
        {"from": deployer.address}
    )
    contracts["Directory"].functions.setDependencies(2, [1]).transact({"from": deployer.address})
    contracts["Directory"].functions.setDependencies(3, [0, 1]).transact({"from": deployer.address})

    contracts["Escrow"].functions.setDiscounts(int(1.06e18), int(1.02e18), int(0.80e18)).transact(
        {"from": deployer.address}
    )
    contracts["Portfolios"].functions.setHaircuts(
        int(1.01e18), int(0.50e18), int(0.95e18)
    ).transact({"from": deployer.address})

    # list currencies
    contracts["Escrow"].functions.listCurrency(v2env.token["DAI"].address, [False, False]).transact(
        {"from": deployer.address}
    )
    contracts["Escrow"].functions.addExchangeRate(
        1, 0, v2env.ethOracle["DAI"].address, int(1.4e18), int(1e18), False
    ).transact({"from": deployer.address})
    contracts["Escrow"].functions.listCurrency(
        v2env.token["USDC"].address, [False, False]
    ).transact({"from": deployer.address})
    contracts["Escrow"].functions.addExchangeRate(
        1, 0, v2env.ethOracle["USDC"].address, int(1.4e18), int(1e18), False
    ).transact({"from": deployer.address})
    contracts["Escrow"].functions.listCurrency(
        v2env.token["WBTC"].address, [False, False]
    ).transact({"from": deployer.address})
    contracts["Escrow"].functions.addExchangeRate(
        1, 0, v2env.ethOracle["WBTC"].address, int(1.4e18), int(1e18), False
    ).transact({"from": deployer.address})

    contracts["DaiCashMarket"] = deploy_proxied_contract(
        "CashMarket",
        artifacts,
        deployer,
        proxyAdmin,
        contracts,
        [contracts["Directory"].address, deployer.address],
    )
    contracts["DaiCashMarket"].functions.initializeDependencies().transact(
        {"from": deployer.address}
    )
    contracts["Portfolios"].functions.createCashGroup(
        2, 2592000 * 3, int(1e9), 1, contracts["DaiCashMarket"].address
    ).transact({"from": deployer.address})

    contracts["DaiCashMarket"].functions.setMaxTradeSize(int(2 ** 127)).transact(
        {"from": deployer.address}
    )
    contracts["DaiCashMarket"].functions.setFee(int(7.5e5), 0).transact({"from": deployer.address})
    contracts["DaiCashMarket"].functions.setRateFactors(int(1.1e9), 85).transact(
        {"from": deployer.address}
    )

    # add liquidity
    v2env.token["DAI"].approve(contracts["Escrow"].address, 2 ** 255)
    contracts["Escrow"].functions.deposit(v2env.token["DAI"].address, int(6100000e18)).transact(
        {"from": deployer.address}
    )
    maturities = contracts["DaiCashMarket"].functions.getActiveMaturities().call()
    for m in maturities:
        contracts["DaiCashMarket"].functions.addLiquidity(
            m, int(3000000e18), int(3000000e18), 0, int(1e9), 2 ** 31
        ).transact({"from": deployer.address})

    return contracts
