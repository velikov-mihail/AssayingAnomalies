function tcosts=fillMissingTcosts(tcosts_raw)

tcosts=tcosts_raw;

load me
load IVOL 
rme = rowrank(me);
rIVOL = rowrank(IVOL);

index3 = isfinite(me + IVOL + tcosts_raw);
index2 = isfinite(me + IVOL) & isnan(tcosts);

for i = 1:rows(tcosts_raw)    
    index = index2(i,:);
    J = find(index == 1);
    
    for k = 1:length(J)
        j = J(k);
        ind = index3(i,:);
        distance = sqrt((rme(i,ind)-rme(i,j)).^2 + (rIVOL(i,ind)-rIVOL(i,j)).^2);
        rank = tiedrank(distance);
        match = find(rank == 1);
        b = tcosts_raw(i,ind);
        if ~isempty(match)
            tcosts(i,j) = b(match(1));
        end
    end
end

index3 = isfinite(me + tcosts_raw);
index2 = isfinite(me) & isnan(tcosts);

for i = 1:rows(tcosts_raw)    
    index = index2(i,:);
    J = find(index == 1);
    
    for k = 1:length(J)
        j = J(k);
        ind = index3(i,:);
        distance = abs(rme(i,ind)-rme(i,j));
        rank = tiedrank(distance);
        match = find(rank == 1);
        b = tcosts_raw(i,ind);
        if ~isempty(match)
            tcosts(i,j) = b(match(1));
        end
    end
end
