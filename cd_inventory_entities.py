import datetime
import json
import typing

import sqlalchemy.orm.exc

from typing import List, Optional

from sqlalchemy import Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, reconstructor
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

    def to_dict(self):
        """Converts the mapped columns of the model instance into a dictionary."""
        # noinspection PyTypeChecker
        return {col.name: getattr(self, col.name) for col in self.__table__.columns}


class Location(Base):
    __tablename__ = 'locations'

    location_id: Mapped[str] = mapped_column(Text, primary_key=True)
    location_description: Mapped[str] = mapped_column(Text)
    location_contents: Mapped[List['CD']] = relationship("CD", back_populates="cd_location")

    def __repr__(self) -> str:
        return self._repr(
            id=self.location_id,
            description=self.location_description
        )


class CD(Base):
    __tablename__ = 'cds'

    cd_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cd_barcode: Mapped[str] = mapped_column(Text, unique=True)
    cd_title: Mapped[Optional[str]] = mapped_column(Text)
    cd_artists: Mapped[Optional[str]] = mapped_column(Text)
    cd_last_seen: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    cd_musicbrainz_release_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)

    cd_location_id: Mapped[Optional[str]] = mapped_column(ForeignKey("locations.location_id"), nullable=True)
    cd_location: Mapped[Optional[Location]] = relationship("Location", back_populates="location_contents")

    def __repr__(self) -> str:
        return self._repr(
            id=self.cd_id,
            barcode=self.cd_barcode,
            title=self.cd_title,
            artist=self.cd_artists,
            release_id=self.cd_musicbrainz_release_id,
            location_id=self.cd_location_id
        )


class BaseWithJson(Base):
    __abstract__ = True

    json_text: Mapped[str] = mapped_column(Text)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._raw_data = None       # do this so PyCharm does not complain about this attribute
        self.zap_properties()

    # need to figure out how to zap _raw_data if the entity is reloaded

    @reconstructor
    def zap_properties(self):
        """This runs when SQLAlchemy loads the entity from the database."""
        self._raw_data = None

    @property
    def raw_data(self):
        if self._raw_data is None:
            self._raw_data = json.loads(self.json_text)
        return self._raw_data


class MP3(BaseWithJson):
    __tablename__ = 'mp3s'

    path: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    track_artists: Mapped[Optional[str]] = mapped_column(Text)
    album_artists: Mapped[Optional[str]] = mapped_column(Text)
    release_id: Mapped[Optional[str]] = mapped_column(Text)
    release_group_id: Mapped[Optional[str]] = mapped_column(Text)
    track_id: Mapped[Optional[str]] = mapped_column(Text)
    recording_id: Mapped[Optional[str]] = mapped_column(Text)
    mtime: Mapped[datetime.datetime] = mapped_column(DateTime)
    encoded_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    updated_time: Mapped[datetime.datetime] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return self._repr(
            path=self.path,
            title=self.title,
            release_id=self.release_id,
        )


class MusicbrainzRelease(BaseWithJson):
    __tablename__ = 'musicbrainz_releases'

    release_id: Mapped[str] = mapped_column(Text, primary_key=True)
    release_group_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    barcode: Mapped[Optional[str]] = mapped_column(Text)
    artists: Mapped[str] = mapped_column(Text)
    catalog_numbers: Mapped[Optional[str]] = mapped_column(Text)

    last_downloaded: Mapped[datetime.datetime] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return self._repr(
            release_id=self.release_id,
            barcode=self.barcode,
            title=self.title,
            artists=self.artists,
            catalog_numbers=self.catalog_numbers,
            release_group_id=self.release_group_id,
        )
