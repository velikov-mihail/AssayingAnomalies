function results = FillMonths(data,persist)

temp = data;
index = find(sum(isfinite(data),2) > 0);
if index(end)-index(end-1) == 12
    for i = 1:rows(index)
        I = index(i);
        for j = 1:11
            if I+j <= rows(data)
                temp(I+j,:) = data(I,:);
            end
        end
    end
else
    if nargin == 1
        persist = 2;
    end
    indexh = sum(isfinite(temp)) > 0;
    index1 = find(indexh == 1);
    for i = 1:cols(index1)
        c = index1(i);
        indexv = isfinite(temp(:,c));
        mm = min(find(indexv == 1));
        MM = max(find(indexv == 1));
        for j = mm+1:min(rows(temp),MM+persist)
            if isfinite(temp(j,c)) == 0
                temp(j,c) = temp(j-1,c);
            end
        end
    end
end

results = temp;