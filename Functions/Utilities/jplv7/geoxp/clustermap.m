function [out,out2]=clustermap(long,lat,dataset,clustnum,method,varargin)
% PURPOSE: This function links a map and a bar plot of the classification variable created by the kmeans method
%------------------------------------------------------------------------
% USAGE: out=clustermap(long,lat,dataset,clustnum,method,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           dataset = n x p matrix of the variables to study
%           clustnum = number of clusters
%           method = clustering method : method=1 :kmeans based on point data
%                                        method=2 : kmeans based on a distance matrix
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%          out2 = group variable
%------------------------------------------------------------------------
% MANUAL: Select points on the map by clicking with the left mouse button
%         Select bars on the bar plot by clicking with the left mouse button
%         You can select points inside a polygon on the map: - right click to set the first point of the polygon
%                                                            - left click to set the other points
%                                                            - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses kmeans.m, kmeans2.m, selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
vectx=[];
vecty=[];

%creation d'un menu pour sauver
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save clusterfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

c=0;
l=0;
symbol=0;
% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% clustering
if method==2
    H=sparse(length(dataset(:,1)),length(dataset(:,1)));
    for i=1:size(dataset,2)
        Tp1=repmat(dataset(:,i)',length(dataset(:,i)),1);
        Tp2=repmat(dataset(:,i),1,length(dataset(:,i)));
        H=H+(Tp2-Tp1).^2;
    end;
    H=sqrt(H);
    [center, U, distortion] = kmeans2(H, clustnum,[nan;nan;0]);
elseif method==1
    [center, U, distortion] = kmeans(dataset, clustnum);
end;
[I,J]=find(U~=0);
class=[1:clustnum];
vectclass=zeros(size(dataset,1),1);
for i=1:clustnum
    vectclass(find(I==class(i)))=i;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

col{1}=[220/255,210/255,183/255];
col{2}=[207/255,203/255,18/255];
col{3}=[240/255,134/255,214/255];
col{4}=[254/255,194/255,203/255];
col{5}=[150/255,118/255,133/255];
col{6}=[132/255,221/255,160/255];
col{7}=[92/255,133/255,94/255];
col{8}=[233/255,168/255,97/255];
col{9}=[121/255,50/255,6/255];
col{10}=[158/255,216/255,235/255];
% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.2 0.6]);
end;
hold on;
for i=1:clustnum
    plot(long(find(vectclass==i)),lat(find(vectclass==i)),'.','Color',col{i});
end;
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%
variable=vectclass;
Numcla=length(variable);

% Trace the barplot
Axis2=subplot(1,2,2);
vsort=sort(variable);
edge=sort(variable)';
edge2=[edge,inf];
N1=histc(variable,edge2);
N1=N1(1:end-1);
N=N1(find(N1~=0));
edge=edge(find(N1~=0));
edgeaff=[0:length(edge)-1];
edge2=[edge,inf];
hold on;
for i=1:clustnum
    Icla=find(variable==i);
    Ncla=histc(variable(Icla),edge);
    Hcla=bar(edgeaff,Ncla,0.6);
    set(Hcla,'FaceColor',col{i});
end;
hold off;
%bar(edgeaff,N,0.6,'b');
%xlabel(name);
 %axis manual;
% set(Axis2,'Xlim',[-1,edgeaff(end)+1]);
% set(Axis2,'Xtick',[0:length(vsort(find(N1~=0)))-1]);
% set(Axis2,'Xticklabel',vsort(find(N1~=0)));
 subplot(Axis1);
 axis manual;
% Xlim2=get(Axis2,'XLim');
% Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%
%Main loop
maptest=0;
bartest=0;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    for i=1:clustnum
    Icla=find(variable==i);
    Ncla=histc(variable(Icla),edge);
    Hcla=bar(edgeaff,Ncla,0.6);
    set(Hcla,'FaceColor',col{i});
    end;
    %bar(edgeaff,N,0.6,'b');
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        if maptest==1
            N2=histc(variable(Iselect),edge);
            bar(edgeaff,N2,0.6,'r');
        elseif bartest==1
            N2=histc(variable(Iselect),edge);
            bar(edgeaff,N2,0.6,'m');
        end;
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
            plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
%     if ~isempty(Iunselect)
%       plot(long(Iunselect),lat(Iunselect),'b.');
%     end;
    for i=1:clustnum
        plot(long(find(vectclass==i)),lat(find(vectclass==i)),'.','Color',col{i});
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'b*');  
            else
                plot(long(Iselect),lat(Iselect),'r.');      
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif bartest==1
            if symbol==1
                 plot(long(Iselect),lat(Iselect),'bo');  
            else
                 plot(long(Iselect),lat(Iselect),'m.');  
            end;           
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%  
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0     
            maptest=1;
            bartest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');
        %%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%
    % bar plot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if bartest==0
            bartest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % bar selection
        if BUTTON~=3 & BUTTON~=2 
            obs=selectstat('bar',obs,variable,edge2,N,x,y,edgeaff);
        end;
        %%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;
out2=variable;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%