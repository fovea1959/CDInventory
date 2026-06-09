import datetime
import typing

import sqlalchemy.orm.exc

from typing import List, Optional

from sqlalchemy import Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship
from sqlalchemy.orm.base import Mapped


class Base(DeclarativeBase):
    def _repr(self, **fields: typing.Dict[str, typing.Any]) -> str:
        # Helper for __repr__
        field_strings = []
        at_least_one_attached_attribute = False
        for key, field in fields.items():
            try:
                field_strings.append(f'{key}={field!r}')
            except sqlalchemy.orm.exc.DetachedInstanceError:
                field_strings.append(f'{key}=DetachedInstanceError')
            else:
                at_least_one_attached_attribute = True
        if at_least_one_attached_attribute:
            return f"<{self.__class__.__name__}({','.join(field_strings)})>"
        return f"<{self.__class__.__name__} {id(self)}>"


class Location(Base):
    __tablename__ = 'locations'

    location_id: Mapped[str] = mapped_column(Text, primary_key=True)
    location_description: Mapped[str] = mapped_column(Text)
    location_contents: Mapped[List['CD']] = relationship("CD", back_populates="cd_location")

    def __repr__(self):
        return self._repr(
            id=self.location_id,
            description=self.location_description
        )


class CD(Base):
    __tablename__ = 'cds'

    cd_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cd_barcode: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    cd_title: Mapped[Optional[str]] = mapped_column(Text)
    cd_artists: Mapped[Optional[str]] = mapped_column(Text)
    cd_last_seen: Mapped[datetime.datetime] = mapped_column(DateTime)

    cd_musicbrainz_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)

    cd_location_id = mapped_column(ForeignKey("locations.location_id"))
    cd_location: Mapped["Location"] = relationship("Location", back_populates="location_contents")

    def __repr__(self):
        return self._repr(
            id=self.cd_id,
            barcode=self.cd_barcode,
            title=self.cd_title,
            artist=self.cd_artists,
            location_id = self.cd_location_id
        )


class BarcodeAlias(Base):
    __tablename__ = 'barcode_aliases'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_encoding: Mapped[str] = mapped_column(Text)
    scan_text: Mapped[str] = mapped_column(Text)
    ean13: Mapped[Optional[str]] = mapped_column(Text)
    musicbrainz_release_id: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("scan_encoding", "scan_text", name="uq_scan"),
    )

    def __repr__(self):
        return self._repr(
            id=self.id,
            encoding=self.scan_encoding,
            text=self.scan_text,
            ean=self.ean13,
            musicbrainz_release_id=self.musicbrainz_release_id
        )
