import enum
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, Integer, \
    String, UnicodeText, func
from sqlalchemy.orm import relationship

from .database import Base

UNKNOWN_OWNER = "Unknown"
HOUSING_DEVAL_FACTOR = 0.0042


class EventType(enum.Enum):
    HOUSING_WARD_INFO = "HOUSING_WARD_INFO"
    # LAND_UPDATE (house sold, reloed, autodemoed, etc)
    #   https://github.com/SapphireServer/Sapphire/blob/master/src/common/Network/PacketDef/Zone/ServerZoneDef.h#L1888
    #   https://github.com/SapphireServer/Sapphire/blob/master/src/world/Manager/HousingMgr.cpp#L365
    # LAND_SET_INITIALIZE (sent on zonein)
    #   https://github.com/SapphireServer/Sapphire/blob/master/src/common/Network/PacketDef/Zone/ServerZoneDef.h#L1943
    #   https://github.com/SapphireServer/Sapphire/blob/master/src/world/Territory/HousingZone.cpp#L197
    # LAND_SET_MAP (sent on zonein, after init, probably the useful one)
    #   https://github.com/SapphireServer/Sapphire/blob/master/src/common/Network/PacketDef/Zone/ServerZoneDef.h#L1929
    #   https://github.com/SapphireServer/Sapphire/blob/master/src/world/Territory/HousingZone.cpp#L154
    # other packets:
    #   LAND_INFO_SIGN (view placard on owned house) - probably not useful, if we get this we already got a LAND_SET_MAP
    #       and if the ward changed since then, we got a LAND_UPDATE
    #   LAND_PRICE_UPDATE (view placard on unowned house) - similar to above, plus spammy if someone is buying a house


# ==== Table defs ====
class Sweeper(Base):
    __tablename__ = "sweepers"

    id = Column(BigInteger, primary_key=True)
    name = Column(String)
    world_id = Column(Integer, ForeignKey("worlds.id"))
    last_seen = Column(DateTime, nullable=True, server_default=func.now(), onupdate=func.now())

    world = relationship("World", back_populates="sweepers")
    sweeps = relationship("WardSweep", back_populates="sweeper")
    events = relationship("Event", back_populates="sweeper")


class World(Base):
    __tablename__ = "worlds"

    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)

    sweepers = relationship("Sweeper", back_populates="world")
    sweeps = relationship("WardSweep", back_populates="world")
    plots = relationship("Plot", back_populates="world")


class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True)  # territoryTypeId
    name = Column(String, unique=True)
    land_set_id = Column(Integer, unique=True, index=True)


class PlotInfo(Base):
    __tablename__ = "plotinfo"

    territory_type_id = Column(Integer, ForeignKey("districts.id"), primary_key=True)
    plot_number = Column(Integer, primary_key=True)

    house_size = Column(Integer)
    house_base_price = Column(Integer)

    district = relationship("District", viewonly=True)


class WardSweep(Base):
    __tablename__ = "wardsweeps"

    id = Column(Integer, primary_key=True)
    sweeper_id = Column(BigInteger, ForeignKey("sweepers.id", ondelete="SET NULL"), nullable=True)
    world_id = Column(Integer, ForeignKey("worlds.id"))
    territory_type_id = Column(Integer, ForeignKey("districts.id"))
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    ward_number = Column(Integer)
    timestamp = Column(DateTime)

    sweeper = relationship("Sweeper", back_populates="sweeps")
    world = relationship("World", back_populates="sweeps")
    plots = relationship("Plot", back_populates="sweep")
    district = relationship("District", viewonly=True)
    event = relationship("Event")


Index("ix_wardsweeps_event_id_desc", WardSweep.event_id.desc())  # NULLS LAST


class Plot(Base):
    __tablename__ = "plots"
    __table_args__ = (
        ForeignKeyConstraint(("territory_type_id", "plot_number"),
                             ("plotinfo.territory_type_id", "plotinfo.plot_number")),
    )

    id = Column(Integer, primary_key=True)
    world_id = Column(Integer, ForeignKey("worlds.id"))
    territory_type_id = Column(Integer, ForeignKey("districts.id"))
    ward_number = Column(Integer)
    plot_number = Column(Integer)
    timestamp = Column(DateTime)
    sweep_id = Column(Integer, ForeignKey("wardsweeps.id", ondelete="SET NULL"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))

    is_owned = Column(Boolean)
    has_built_house = Column(Boolean)  # used to determine if a plot was reloed into or bought (not super accurate)
    house_price = Column(Integer, nullable=True)  # null for unknown price
    owner_name = Column(String, nullable=True)  # "Unknown" for unknown owner (UNKNOWN_OWNER), used to build relo graph

    sweep = relationship("WardSweep", back_populates="plots")
    event = relationship("Event", back_populates="plots")
    world = relationship("World", back_populates="plots")
    district = relationship("District", viewonly=True)
    plot_info = relationship("PlotInfo", viewonly=True)

    @property
    def num_devals(self) -> Optional[int]:
        """
        Returns the number of price this house has devalued. If the price is unknown, returns None.
        If price>max, returns 0.
        """
        if self.house_price is None:
            return None
        max_price = self.plot_info.house_base_price
        if self.house_price >= max_price:
            return 0
        return round((max_price - self.house_price) / (HOUSING_DEVAL_FACTOR * max_price))


# common query indices
Index("ix_plots_world_id_territory_type_id_ward_number_plot_number",
      Plot.world_id, Plot.territory_type_id, Plot.ward_number, Plot.plot_number)
Index("ix_plots_ward_number_plot_number_timestamp_desc", Plot.ward_number, Plot.plot_number, Plot.timestamp.desc())
# FK indices
Index("ix_plots_sweep_id_desc", Plot.sweep_id.desc())
Index("ix_plots_event_id_desc", Plot.event_id.desc())
Index("ix_plots_timestamp_desc", Plot.timestamp.desc())


# store of all ingested events for later analysis (e.g. FC/player ownership, relocation/resell graphs, etc)
class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    sweeper_id = Column(BigInteger, ForeignKey("sweepers.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, index=True)
    event_type = Column(Enum(EventType), index=True)
    data = Column(UnicodeText)

    sweeper = relationship("Sweeper", back_populates="events")
    plots = relationship("Plot", back_populates="event", cascade="all, delete", passive_deletes=True)
