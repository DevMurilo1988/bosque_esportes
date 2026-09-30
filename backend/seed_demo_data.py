import argparse
import calendar
from datetime import date, datetime, timedelta

from main import conectar_banco


CLIENT_PREFIX = "DEMO"
PAYMENT_METHODS = ("PIX", "Dinheiro", "Cartão", "Outro")
BOOKING_STATUSES = (
    "Confirmado",
    "Pendente",
    "Cancelado",
    "Não atendido",
)


def parse_month(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m")
        if parsed.strftime("%Y-%m") != value:
            raise ValueError
        return parsed.year, parsed.month
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use o formato AAAA-MM.") from error


def add_client(cursor, month_label, number):
    name = f"{CLIENT_PREFIX} {month_label} - Cliente {number:02d}"
    contact = f"0000000{number:04d}"
    cursor.execute(
        """
        INSERT INTO cliente
            (nome, contato, garantia_reserva, motivo_garantia)
        VALUES (%s, %s, 'Dispensado', NULL)
        """,
        (name, contact),
    )
    return cursor.lastrowid


def add_booking(cursor, client_id, court, day, hour, status, queue_confirmed_id=None):
    hourly_value = float(court["valor"] or 0)
    fee = float(court["taxa_reserva"] or 0)
    remaining = max(hourly_value - fee, 0)
    cursor.execute(
        """
        INSERT INTO agendamento
            (cliente_id, quadra_id, data, horario, valor_hora,
             taxa_reserva, valor_restante, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            client_id,
            court["id"],
            day,
            f"{hour:02d}:00:00",
            hourly_value,
            fee,
            remaining,
            status,
        ),
    )
    booking_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO historico_status_agendamento
            (agendamento_id, status_anterior, status_novo)
        VALUES (%s, 'Novo', 'Pendente')
        """,
        (booking_id,),
    )
    if status != "Pendente":
        cursor.execute(
            """
            INSERT INTO historico_status_agendamento
                (agendamento_id, status_anterior, status_novo)
            VALUES (%s, 'Pendente', %s)
            """,
            (booking_id, status),
        )
    if status == "Não atendido" and queue_confirmed_id:
        cursor.execute(
            """
            INSERT INTO agendamento_fila_retorno
                (agendamento_id, confirmado_id)
            VALUES (%s, %s)
            """,
            (booking_id, queue_confirmed_id),
        )
    return booking_id


def add_payment(
    cursor,
    client_id,
    court_value,
    fee,
    booking_id=None,
    membership_id=None,
    competence=None,
    paid=0,
    status="Pendente",
    payment_date=None,
    method=None,
    note=None,
):
    amount = float(court_value)
    fee = float(fee)
    total = amount + fee
    cursor.execute(
        """
        INSERT INTO pagamento
            (cliente_id, agendamento_id, mensalidade_id, competencia,
             tipo, valor, taxa_reserva, valor_total, valor_pago,
             data_pagamento, forma_pagamento, status, observacao)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            client_id,
            booking_id,
            membership_id,
            competence,
            "Reserva" if booking_id else "Mensalidade",
            amount,
            fee,
            total,
            paid,
            payment_date,
            method,
            status,
            note,
        ),
    )
    payment_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO historico_status_pagamento
            (pagamento_id, status_anterior, status_novo)
        VALUES (%s, 'Novo', %s)
        """,
        (payment_id, status),
    )
    return payment_id


def seed_month(cursor, year, month):
    month_label = f"{year:04d}-{month:02d}"
    days_in_month = calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)

    cursor.execute(
        """
        SELECT id, nome, tipo, valor, valor_mensal, taxa_reserva
        FROM quadra
        WHERE ativo = 1
        ORDER BY id
        """
    )
    courts = [
        {
            "id": row[0],
            "nome": row[1],
            "tipo": row[2],
            "valor": row[3],
            "valor_mensal": row[4],
            "taxa_reserva": row[5],
        }
        for row in cursor.fetchall()
    ]
    if not courts:
        raise RuntimeError("Não há quadras ativas para preencher com dados.")

    cursor.execute(
        """
        SELECT chave, valor
        FROM configuracao
        WHERE chave IN (
            'horario_abertura_semana',
            'horario_fechamento_semana',
            'horario_abertura_domingo',
            'horario_fechamento_domingo',
            'permitir_fila',
            'limite_fila'
        )
        """
    )
    settings = dict(cursor.fetchall())
    weekday_open = settings.get("horario_abertura_semana", "08:00")
    weekday_close = settings.get("horario_fechamento_semana", "00:00")
    sunday_open = settings.get("horario_abertura_domingo", "07:00")
    sunday_close = settings.get("horario_fechamento_domingo", "17:00")
    try:
        queue_limit = int(float(settings.get("limite_fila", "3")))
    except (TypeError, ValueError):
        queue_limit = 3
    queue_enabled = str(settings.get("permitir_fila", "1")).lower() in (
        "1",
        "true",
        "sim",
    )
    if not queue_enabled:
        queue_limit = 1

    client_ids = [
        add_client(cursor, month_label, index)
        for index in range(1, 25)
    ]
    booking_count = 0
    booking_status_count = {status: 0 for status in BOOKING_STATUSES}
    payment_count = 0
    payment_status_count = {"Recebido": 0, "Pendente": 0, "Cancelado": 0}
    monthly_membership_count = 0

    special_slots = {
        (last_day, courts[0]["id"], 21),
        (last_day, courts[1]["id"], 22),
        (last_day, courts[2]["id"], 22),
        (last_day, courts[3]["id"], 19),
    }

    for offset in range(days_in_month):
        day = first_day + timedelta(days=offset)
        sunday = day.weekday() == 6
        opening = int((sunday and sunday_open or weekday_open).split(":")[0])
        closing_text = sunday and sunday_close or weekday_close
        closing = int(closing_text.split(":")[0])
        if closing == 0:
            closing = 24
        if sunday:
            base_hours = [hour for hour in (8, 11, 14, 16) if opening <= hour < closing]
        else:
            base_hours = [hour for hour in (9, 13, 18, 21) if opening <= hour < closing]

        for court_index, court in enumerate(courts):
            # Three different slots per court/day create a useful monthly
            # history while keeping the data set manageable.
            hours = base_hours[:3]
            if len(hours) < 3:
                hours = list(range(opening, closing))[:3]
            for slot_index, hour in enumerate(hours):
                if (day, court["id"], hour) in special_slots:
                    continue
                status = BOOKING_STATUSES[
                    (day.day * 3 + court_index + slot_index) % len(BOOKING_STATUSES)
                ]
                client_id = client_ids[
                    (day.day * 7 + court_index * 5 + slot_index) % len(client_ids)
                ]
                booking_id = add_booking(
                    cursor,
                    client_id,
                    court,
                    day,
                    hour,
                    status,
                )
                booking_count += 1
                booking_status_count[status] += 1

                should_create_payment = (
                    status == "Confirmado"
                    or status == "Cancelado"
                    or (
                        status == "Pendente"
                        and (day.day + court_index + slot_index) % 2 == 0
                    )
                )
                if not should_create_payment:
                    continue

                total = float(court["valor"] or 0)
                fee = float(court["taxa_reserva"] or 0)
                amount = max(total - fee, 0)
                if status == "Confirmado":
                    if fee > 0 and (day.day + slot_index) % 3 == 0:
                        paid = fee
                        payment_status = "Pendente"
                    elif total > 0 and (day.day + slot_index) % 5 == 0:
                        paid = round(total / 2, 2)
                        payment_status = "Pendente"
                    else:
                        paid = total
                        payment_status = "Recebido"
                elif status == "Pendente":
                    paid = fee if fee > 0 and (day.day + slot_index) % 4 == 0 else 0
                    payment_status = "Pendente"
                else:
                    paid = 0
                    payment_status = "Cancelado"
                payment_date = day if paid > 0 else None
                method = (
                    PAYMENT_METHODS[(day.day + court_index) % len(PAYMENT_METHODS)]
                    if paid > 0
                    else None
                )
                add_payment(
                    cursor,
                    client_id,
                    amount,
                    fee,
                    booking_id=booking_id,
                    paid=paid,
                    status=payment_status,
                    payment_date=payment_date,
                    method=method,
                    note=f"Simulação {month_label}: {payment_status.lower()}",
                )
                payment_count += 1
                payment_status_count[payment_status] += 1

    # The last day has deliberate live scenarios for queue, cancellation,
    # fee collection and follow-up in the admin panel.
    last_day_cases = (
        (courts[0], 21, ("Confirmado", "Não atendido", "Não atendido")),
        (courts[1], 22, ("Pendente", "Pendente", "Pendente")),
        (courts[2], 22, ("Pendente", "Cancelado")),
        (courts[3], 19, ("Confirmado", "Não atendido", "Não atendido")),
    )
    for case_index, (court, hour, statuses) in enumerate(last_day_cases):
        if len(statuses) > queue_limit and statuses[0] == "Pendente":
            statuses = statuses[:queue_limit]
        primary_booking_id = None
        for request_index, status in enumerate(statuses):
            client_id = client_ids[(case_index * 5 + request_index + 20) % len(client_ids)]
            booking_id = add_booking(
                cursor,
                client_id,
                court,
                last_day,
                hour,
                status,
                queue_confirmed_id=primary_booking_id,
            )
            if status == "Confirmado":
                primary_booking_id = booking_id
            booking_count += 1
            booking_status_count[status] += 1

            fee = float(court["taxa_reserva"] or 0)
            total = float(court["valor"] or 0)
            if status == "Confirmado":
                paid = fee
                payment_status = "Pendente" if paid < total else "Recebido"
            elif status == "Pendente" and request_index == 1:
                paid = fee if fee > 0 else round(total * 0.25, 2)
                payment_status = "Pendente"
            elif status == "Cancelado":
                paid = 0
                payment_status = "Cancelado"
            else:
                continue
            add_payment(
                cursor,
                client_id,
                max(total - fee, 0),
                fee,
                booking_id=booking_id,
                paid=paid,
                status=payment_status,
                payment_date=last_day if paid else None,
                method="PIX" if paid else None,
                note=f"Simulação de atendimento {month_label}",
            )
            payment_count += 1
            payment_status_count[payment_status] += 1

    memberships = []
    membership_specs = []
    for index, court in enumerate(courts):
        weekday = index + 1
        candidate_start = first_day
        while (candidate_start.weekday() + 1) % 7 != weekday:
            candidate_start += timedelta(days=1)
        membership_specs.append(
            {
                "court": court,
                "weekday": weekday,
                "client_id": client_ids[index],
                "start": first_day,
                "end": date(year, month, min(24 if index == len(courts) - 1 else days_in_month, days_in_month))
                if index == len(courts) - 1
                else None,
                "status": "Encerrada" if index == len(courts) - 1 else "Ativa",
            }
        )

    for index, spec in enumerate(membership_specs):
        court = spec["court"]
        monthly_value = float(court["valor_mensal"] or 0)
        if monthly_value <= 0:
            monthly_value = max(float(court["valor"] or 0) * 8, 100)
        cursor.execute(
            """
            INSERT INTO mensalidade
                (cliente_id, quadra_id, dia_semana, horario, valor_mensal,
                 data_inicio, data_encerramento, observacao, status)
            VALUES (%s, %s, %s, '17:30:00', %s, %s, %s, %s, %s)
            """,
            (
                spec["client_id"],
                court["id"],
                spec["weekday"],
                monthly_value,
                spec["start"],
                spec["end"],
                f"Simulação {month_label} - mensalista de teste",
                spec["status"],
            ),
        )
        membership_id = cursor.lastrowid
        memberships.append((membership_id, spec, monthly_value))
        monthly_membership_count += 1

    for index, (membership_id, spec, monthly_value) in enumerate(memberships):
        client_id = spec["client_id"]
        if index == 0:
            add_payment(
                cursor,
                client_id,
                monthly_value,
                0,
                membership_id=membership_id,
                competence=month_label,
                paid=monthly_value,
                status="Recebido",
                payment_date=last_day,
                method="PIX",
                note=f"Mensalidade simulada quitada em {month_label}",
            )
            payment_count += 1
            payment_status_count["Recebido"] += 1
        elif index == 1:
            add_payment(
                cursor,
                client_id,
                monthly_value,
                0,
                membership_id=membership_id,
                competence=month_label,
                paid=round(monthly_value / 4, 2),
                status="Pendente",
                payment_date=last_day,
                method="Dinheiro",
                note=f"Mensalidade simulada com saldo pendente em {month_label}",
            )
            payment_count += 1
            payment_status_count["Pendente"] += 1
        elif index == 2:
            add_payment(
                cursor,
                client_id,
                monthly_value,
                0,
                membership_id=membership_id,
                competence=month_label,
                paid=0,
                status="Cancelado",
                note=f"Registro cancelado de teste em {month_label}",
            )
            payment_count += 1
            payment_status_count["Cancelado"] += 1
            add_payment(
                cursor,
                client_id,
                monthly_value,
                0,
                membership_id=membership_id,
                competence=month_label,
                paid=monthly_value,
                status="Recebido",
                payment_date=last_day,
                method="Cartão",
                note=f"Mensalidade simulada quitada após correção em {month_label}",
            )
            payment_count += 1
            payment_status_count["Recebido"] += 1
        else:
            add_payment(
                cursor,
                client_id,
                monthly_value,
                0,
                membership_id=membership_id,
                competence=month_label,
                paid=0,
                status="Pendente",
                note=f"Mensalidade simulada aguardando recebimento em {month_label}",
            )
            payment_count += 1
            payment_status_count["Pendente"] += 1

    return {
        "period": f"{first_day.isoformat()}..{last_day.isoformat()}",
        "courts": len(courts),
        "demo_clients": len(client_ids),
        "bookings": booking_count,
        "booking_statuses": booking_status_count,
        "memberships": monthly_membership_count,
        "payments": payment_count,
        "payment_statuses": payment_status_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Substitui reservas, mensalidades e pagamentos por um conjunto "
            "de demonstração, preservando quadras, configurações e admins."
        )
    )
    parser.add_argument("--month", type=parse_month, required=True, help="Mês de simulação no formato AAAA-MM.")
    parser.add_argument(
        "--replace-operational-data",
        action="store_true",
        help="Confirma a remoção dos registros operacionais existentes.",
    )
    args = parser.parse_args()
    if not args.replace_operational_data:
        parser.error(
            "A ação remove reservas, mensalidades, pagamentos e seus históricos. "
            "Repita com --replace-operational-data após confirmar o escopo."
        )

    year, month = args.month
    month_label = f"{year:04d}-{month:02d}"
    connection = conectar_banco()
    cursor = connection.cursor()
    try:
        connection.start_transaction()
        cursor.execute("DELETE FROM agendamento_fila_retorno")
        cursor.execute("DELETE FROM historico_status_pagamento")
        cursor.execute("DELETE FROM pagamento_mensalidade")
        cursor.execute("DELETE FROM pagamento")
        cursor.execute("DELETE FROM historico_status_agendamento")
        cursor.execute("DELETE FROM agendamento")
        cursor.execute("DELETE FROM mensalidade")
        cursor.execute(
            "DELETE FROM cliente WHERE nome LIKE %s",
            (f"{CLIENT_PREFIX} %",),
        )
        summary = seed_month(cursor, year, month)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

    print(f"Dados de demonstração gravados para {summary['period']}.")
    for key, value in summary.items():
        if key != "period":
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
