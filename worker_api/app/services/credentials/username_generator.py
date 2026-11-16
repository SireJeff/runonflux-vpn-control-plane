"""Non-leaking end-user username generator.

Produces memorable usernames of the form ``<figure>_<4hex>`` drawn from a
curated list of literary/historical/scientific figures. The figure leaks
nothing about the reseller or the platform, and the hex suffix guarantees
per-reseller uniqueness (enforced by the ``uq_admin_user`` constraint on
``(admin_id, username)``).

New users only — existing users keep their names.
"""

import secrets

# Curated, romanized-ASCII, <=14 chars, deduplicated. Weighted to broadly
# admired literary / historical / scientific figures; living/contemporary
# politicians are deliberately excluded for audience safety.
# (User-approved 2026-06-24 — ship verbatim.)
FIGURES = (
    # Persian / Eastern literary
    "rumi",
    "hafez",
    "saadi",
    "ferdowsi",
    "khayyam",
    "attar",
    "nizami",
    "sanaei",
    "khaghani",
    "mutanabbi",
    "maarri",
    "tagore",
    "ghalib",
    "iqbal",
    "laozi",
    "confucius",
    "mencius",
    "bodhidharma",
    "nagarjuna",
    "shantideva",
    "xuanzang",
    # Ancient philosophy / science
    "socrates",
    "plato",
    "aristotle",
    "pythagoras",
    "euclid",
    "archimedes",
    "herodotus",
    "thucydides",
    "hippocrates",
    "galen",
    "seneca",
    "epictetus",
    "cicero",
    "marcus",
    "aurelius",
    # Scientists
    "newton",
    "leibniz",
    "gauss",
    "euler",
    "riemann",
    "maxwell",
    "faraday",
    "bohr",
    "planck",
    "curie",
    "pasteur",
    "mendel",
    "tesla",
    "edison",
    "galileo",
    "kepler",
    "darwin",
    "mendeleev",
    "lovelace",
    "turing",
    "feynman",
    "nobel",
    "fleming",
    "lister",
    "halley",
    "hubble",
    "oppenheimer",
    # Writers / philosophers
    "homer",
    "dante",
    "virgil",
    "ovid",
    "cervantes",
    "shakespeare",
    "milton",
    "moliere",
    "goethe",
    "schiller",
    "austen",
    "dickens",
    "tolstoy",
    "dostoevsky",
    "chekhov",
    "gogol",
    "turgenev",
    "proust",
    "kafka",
    "camus",
    "sartre",
    "nietzsche",
    "kierkegaard",
    "hegel",
    "kant",
    "spinoza",
    "descartes",
    "pascal",
    "hume",
    "locke",
    "rousseau",
    "voltaire",
    "montaigne",
    "flaubert",
    "balzac",
    "hugo",
    "dumas",
    "verne",
    "zola",
    "maupassant",
    "wilde",
    "ibsen",
    "joyce",
    "woolf",
    "orwell",
    "huxley",
    "borges",
    "marquez",
    "neruda",
    "frost",
    "whitman",
    "emerson",
    "thoreau",
    "poe",
    # Composers
    "bach",
    "mozart",
    "beethoven",
    "chopin",
    "liszt",
    "handel",
    "haydn",
    "schubert",
    "brahms",
    "mahler",
    "wagner",
    "verdi",
    "rossini",
    "vivaldi",
    "puccini",
    "debussy",
    "stravinsky",
    "scarlatti",
    "monteverdi",
    # Artists
    "raphael",
    "donatello",
    "botticelli",
    "leonardo",
    "michelangelo",
    "rembrandt",
    "vermeer",
    "goya",
    "velazquez",
    "monet",
    "manet",
    "renoir",
    "cezanne",
    "matisse",
    "picasso",
    "klimt",
    "hokusai",
    "hiroshige",
    "ghiberti",
    # Historical (deceased, broadly admired)
    "gandhi",
    "mandela",
    "lincoln",
    "joan",
    "hypatia",
    "cleopatra",
)


def username_taken(db, username: str, exclude_user_id: int | None = None) -> bool:
    """True if any non-deleted end user of ANY reseller holds ``username``,
    compared case-insensitively.

    Usernames are a global namespace: VPN containers key Xray clients by
    ``email = username`` across all resellers, and Xray compares emails
    case-insensitively, so one collision makes Xray reject its whole config
    (crash-looped every VLESS/Trojan container, 2026-10-24).
    """
    from sqlalchemy import func

    from app.models.admin_users import AdminUser

    conditions = [
        func.lower(AdminUser.username) == username.lower(),
        # IS DISTINCT FROM: a NULL status still occupies the name (`!=` would
        # silently skip it). Mirrors the uq_admin_users_username_ci predicate.
        AdminUser.status.is_distinct_from("deleted"),
    ]
    if exclude_user_id is not None:
        conditions.append(AdminUser.id != exclude_user_id)
    return db.query(AdminUser.id).filter(*conditions).first() is not None


def generate_unique_username(db, admin_id: int, max_attempts: int = 50) -> str:
    """Return a unique ``<figure>_<4hex>`` username for the given reseller.

    Checks each candidate against ALL resellers (see ``username_taken``) and
    retries on collision. Raises ``RuntimeError`` if no unique name is found in
    ``max_attempts`` (astronomically unlikely: ~160 figures x 65536 suffixes).
    """
    for _ in range(max_attempts):
        figure = secrets.choice(FIGURES)
        suffix = secrets.token_hex(2)  # 4 hex chars
        candidate = f"{figure}_{suffix}"
        if not username_taken(db, candidate):
            return candidate
    raise RuntimeError(
        "username generation exhausted: could not find a unique name "
        f"for admin_id={admin_id} in {max_attempts} attempts"
    )
